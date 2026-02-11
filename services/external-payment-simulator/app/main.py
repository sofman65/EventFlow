import hashlib
import hmac
import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from decimal import Decimal
from threading import Event, Lock, Thread
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

import requests
from fastapi import FastAPI, HTTPException, status
from prometheus_client import Counter, Histogram, make_asgi_app
from pydantic import BaseModel, ConfigDict, Field


logger = logging.getLogger("external-payment-simulator")


def parse_bool(env_name: str, default: bool = False) -> bool:
    raw = os.getenv(env_name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def parse_probability(env_name: str, default: str) -> float:
    try:
        value = float(os.getenv(env_name, default))
    except ValueError:
        value = float(default)
    return max(0.0, min(1.0, value))


def parse_positive_float(env_name: str, default: str) -> float:
    try:
        value = float(os.getenv(env_name, default))
    except ValueError:
        value = float(default)
    return max(0.1, value)


def parse_positive_decimal(env_name: str, default: str) -> Decimal:
    raw_value = os.getenv(env_name, default)
    try:
        value = Decimal(raw_value)
    except Exception:
        value = Decimal(default)
    if value <= 0:
        return Decimal(default)
    return value


WEBHOOK_URL = os.getenv(
    "EVENTFLOW_WEBHOOK_URL",
    "http://localhost:8000/api/webhooks/payment-authorized",
)
WEBHOOK_SIGNING_SECRET = os.getenv(
    "EVENTFLOW_WEBHOOK_SIGNING_SECRET",
    "eventflow-local-secret",
)
WEBHOOK_TIMEOUT_SECONDS = float(os.getenv("SIMULATOR_WEBHOOK_TIMEOUT_SECONDS", "3"))
MAX_ATTEMPTS = max(1, int(os.getenv("SIMULATOR_MAX_ATTEMPTS", "4")))
BACKOFF_BASE_SECONDS = float(os.getenv("SIMULATOR_BACKOFF_BASE_SECONDS", "0.5"))
BACKOFF_MAX_SECONDS = float(os.getenv("SIMULATOR_BACKOFF_MAX_SECONDS", "5"))
BACKOFF_JITTER_SECONDS = float(os.getenv("SIMULATOR_BACKOFF_JITTER_SECONDS", "0.25"))
DUPLICATE_RATE = parse_probability("SIMULATOR_DUPLICATE_RATE", "0.05")
CORRUPTION_RATE = parse_probability("SIMULATOR_CORRUPTION_RATE", "0.01")
AUTO_STREAM_ENABLED = parse_bool("SIMULATOR_AUTO_STREAM_ENABLED", False)
AUTO_STREAM_RPS = parse_positive_float("SIMULATOR_AUTO_STREAM_RPS", "5")
AUTO_STREAM_INTERVAL_SECONDS = 1.0 / AUTO_STREAM_RPS
AUTO_STREAM_AMOUNT = parse_positive_decimal("SIMULATOR_AUTO_STREAM_AMOUNT", "49.90")
AUTO_STREAM_CURRENCY = os.getenv("SIMULATOR_AUTO_STREAM_CURRENCY", "USD").upper()
AUTO_STREAM_PAYMENT_PREFIX = os.getenv(
    "SIMULATOR_AUTO_STREAM_PAYMENT_PREFIX",
    "pay_stream",
)
AUTO_STREAM_ORDER_PREFIX = os.getenv(
    "SIMULATOR_AUTO_STREAM_ORDER_PREFIX",
    "ord_stream",
)

auto_stream_stop_event = Event()
auto_stream_thread: Optional[Thread] = None
auto_stream_counter_lock = Lock()
auto_stream_counter = 0

AUTHORIZE_REQUESTS_TOTAL = Counter(
    "eventflow_simulator_authorize_requests_total",
    "Total authorize requests accepted by the external simulator.",
    ["result"],
)
WEBHOOK_ATTEMPTS_TOTAL = Counter(
    "eventflow_simulator_webhook_attempts_total",
    "Total webhook delivery attempts performed by the external simulator.",
    ["result", "status_class"],
)
WEBHOOK_RETRIES_TOTAL = Counter(
    "eventflow_simulator_webhook_retries_total",
    "Total webhook retries performed by the external simulator.",
)
PAYLOAD_CORRUPTED_TOTAL = Counter(
    "eventflow_simulator_payload_corrupted_total",
    "Total events intentionally corrupted by the simulator fault injector.",
    ["mode"],
)
DUPLICATE_EVENTS_TOTAL = Counter(
    "eventflow_simulator_duplicate_events_total",
    "Total duplicate webhooks intentionally sent by the simulator.",
)
WEBHOOK_LATENCY_SECONDS = Histogram(
    "eventflow_simulator_webhook_latency_seconds",
    "Webhook delivery latency from simulator to EventFlow API.",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)
AUTO_STREAM_EVENTS_TOTAL = Counter(
    "eventflow_simulator_auto_stream_events_total",
    "Total authorization events emitted by simulator auto-stream mode.",
    ["result"],
)


class AuthorizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_id: str = Field(..., min_length=1)
    order_id: str = Field(..., min_length=1)
    amount: Decimal = Field(..., gt=0)
    currency: str = Field(..., pattern="^[A-Z]{3}$")
    force_duplicate: bool = False
    force_corruption: bool = False


def build_signature(raw_body: bytes, timestamp: int) -> str:
    signed_payload = f"{timestamp}.".encode("utf-8") + raw_body
    digest = hmac.new(
        WEBHOOK_SIGNING_SECRET.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    )
    return digest.hexdigest()


def build_event(payload: AuthorizeRequest) -> Dict[str, Any]:
    return {
        "event_id": str(uuid4()),
        "event_type": "payment.authorized.v1",
        "schema_version": 1,
        "source": "external-payment-simulator",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "payment_id": payload.payment_id,
            "order_id": payload.order_id,
            "amount": float(payload.amount),
            "currency": payload.currency,
            "provider_auth_id": f"auth_{uuid4().hex[:12]}",
        },
    }


def corrupt_event(event: Dict[str, Any]) -> str:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return "payload_not_object"

    mode = random.choice(
        (
            "missing_provider_auth_id",
            "negative_amount",
            "blank_order_id",
            "currency_lowercase",
        )
    )

    if mode == "missing_provider_auth_id":
        payload.pop("provider_auth_id", None)
    elif mode == "negative_amount":
        payload["amount"] = -1
    elif mode == "blank_order_id":
        payload["order_id"] = ""
    elif mode == "currency_lowercase":
        currency = str(payload.get("currency", "USD"))
        payload["currency"] = currency.lower()

    return mode


def build_headers(raw_body: bytes) -> Dict[str, str]:
    timestamp = int(time.time())
    signature = build_signature(raw_body, timestamp)
    return {
        "Content-Type": "application/json",
        "X-Provider-Timestamp": str(timestamp),
        "X-Provider-Signature": signature,
    }


def status_class(status_code: int) -> str:
    return f"{status_code // 100}xx"


def send_webhook_once(event: Dict[str, Any]) -> Tuple[bool, Optional[int], str]:
    raw_body = json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = build_headers(raw_body)
    started_at = time.perf_counter()

    try:
        response = requests.post(
            WEBHOOK_URL,
            data=raw_body,
            headers=headers,
            timeout=WEBHOOK_TIMEOUT_SECONDS,
        )
        WEBHOOK_LATENCY_SECONDS.observe(time.perf_counter() - started_at)

        if 200 <= response.status_code < 300:
            WEBHOOK_ATTEMPTS_TOTAL.labels(
                result="success",
                status_class=status_class(response.status_code),
            ).inc()
            return True, response.status_code, response.text

        WEBHOOK_ATTEMPTS_TOTAL.labels(
            result="http_error",
            status_class=status_class(response.status_code),
        ).inc()
        return False, response.status_code, response.text
    except requests.RequestException as exc:
        WEBHOOK_LATENCY_SECONDS.observe(time.perf_counter() - started_at)
        WEBHOOK_ATTEMPTS_TOTAL.labels(
            result="network_error",
            status_class="n/a",
        ).inc()
        return False, None, str(exc)


def deliver_with_retries(event: Dict[str, Any]) -> Dict[str, Any]:
    last_status: Optional[int] = None
    last_error = "unknown failure"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        ok, response_status, response_text = send_webhook_once(event)
        if ok:
            return {
                "ok": True,
                "attempts": attempt,
                "status_code": response_status,
                "message": response_text,
            }

        last_status = response_status
        last_error = response_text

        if attempt < MAX_ATTEMPTS:
            WEBHOOK_RETRIES_TOTAL.inc()
            backoff_seconds = min(
                BACKOFF_MAX_SECONDS,
                BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)),
            )
            backoff_seconds += random.uniform(0, BACKOFF_JITTER_SECONDS)
            time.sleep(backoff_seconds)

    return {
        "ok": False,
        "attempts": MAX_ATTEMPTS,
        "status_code": last_status,
        "message": last_error,
    }


def process_authorize_request(request: AuthorizeRequest) -> Dict[str, Any]:
    event = build_event(request)

    should_corrupt = request.force_corruption or (random.random() < CORRUPTION_RATE)
    corruption_mode: Optional[str] = None
    if should_corrupt:
        corruption_mode = corrupt_event(event)
        PAYLOAD_CORRUPTED_TOTAL.labels(mode=corruption_mode).inc()

    primary_delivery = deliver_with_retries(event)
    if not primary_delivery["ok"]:
        AUTHORIZE_REQUESTS_TOTAL.labels(result="failed").inc()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "status": "delivery_failed",
                "event_id": event.get("event_id"),
                "attempts": primary_delivery["attempts"],
                "webhook_url": WEBHOOK_URL,
                "last_status_code": primary_delivery["status_code"],
                "last_error": primary_delivery["message"],
            },
        )

    duplicate_requested = request.force_duplicate or (random.random() < DUPLICATE_RATE)
    duplicate_delivery: Optional[Dict[str, Any]] = None
    if duplicate_requested:
        DUPLICATE_EVENTS_TOTAL.inc()
        duplicate_delivery = deliver_with_retries(event)

    AUTHORIZE_REQUESTS_TOTAL.labels(result="accepted").inc()
    return {
        "status": "accepted",
        "event_id": event["event_id"],
        "corrupted": should_corrupt,
        "corruption_mode": corruption_mode,
        "primary_delivery": primary_delivery,
        "duplicate_sent": duplicate_requested,
        "duplicate_delivery": duplicate_delivery,
    }


def next_auto_stream_index() -> int:
    global auto_stream_counter
    with auto_stream_counter_lock:
        auto_stream_counter += 1
        return auto_stream_counter


def build_auto_stream_request(index: int) -> AuthorizeRequest:
    return AuthorizeRequest(
        payment_id=f"{AUTO_STREAM_PAYMENT_PREFIX}_{index}",
        order_id=f"{AUTO_STREAM_ORDER_PREFIX}_{index}",
        amount=AUTO_STREAM_AMOUNT,
        currency=AUTO_STREAM_CURRENCY,
    )


def auto_stream_loop() -> None:
    logger.info(
        "Auto-stream enabled at %.2f events/sec (interval %.3fs)",
        AUTO_STREAM_RPS,
        AUTO_STREAM_INTERVAL_SECONDS,
    )
    while not auto_stream_stop_event.is_set():
        index = next_auto_stream_index()
        try:
            request = build_auto_stream_request(index)
            process_authorize_request(request)
            AUTO_STREAM_EVENTS_TOTAL.labels(result="accepted").inc()
        except HTTPException as http_error:
            AUTO_STREAM_EVENTS_TOTAL.labels(result="failed").inc()
            logger.warning(
                "Auto-stream delivery failed (status=%s): %s",
                http_error.status_code,
                http_error.detail,
            )
        except Exception as unexpected_error:
            AUTO_STREAM_EVENTS_TOTAL.labels(result="failed").inc()
            logger.exception("Auto-stream unexpected failure: %s", unexpected_error)

        auto_stream_stop_event.wait(AUTO_STREAM_INTERVAL_SECONDS)


app = FastAPI(title="External Payment Simulator")
app.mount("/metrics", make_asgi_app())


@app.on_event("startup")
def on_startup() -> None:
    global auto_stream_thread
    if not AUTO_STREAM_ENABLED:
        return

    auto_stream_stop_event.clear()
    auto_stream_thread = Thread(target=auto_stream_loop, name="auto-stream", daemon=True)
    auto_stream_thread.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    auto_stream_stop_event.set()
    if auto_stream_thread is not None and auto_stream_thread.is_alive():
        auto_stream_thread.join(timeout=5)


@app.get("/health")
def health() -> Dict[str, str]:
    return {
        "status": "ok",
        "auto_stream_enabled": "true" if AUTO_STREAM_ENABLED else "false",
        "auto_stream_rps": f"{AUTO_STREAM_RPS:.2f}",
    }


@app.post("/authorize")
def authorize(request: AuthorizeRequest) -> Dict[str, Any]:
    return process_authorize_request(request)
