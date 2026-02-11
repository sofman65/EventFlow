import hashlib
import hmac
import json
import os
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.kafka.producer import publish_raw_event

router = APIRouter()

WEBHOOK_SECRET = os.getenv("PAYMENT_PROVIDER_WEBHOOK_SECRET", "eventflow-local-secret")
WEBHOOK_MAX_AGE_SECONDS = int(
    os.getenv("PAYMENT_PROVIDER_WEBHOOK_MAX_AGE_SECONDS", "300")
)


def compute_signature(raw_body: bytes, timestamp: int) -> str:
    signed_payload = f"{timestamp}.".encode("utf-8") + raw_body
    digest = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    )
    return digest.hexdigest()


def verify_signature(raw_body: bytes, signature: str, timestamp_raw: str) -> int:
    try:
        timestamp = int(timestamp_raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid X-Provider-Timestamp header",
        ) from exc

    now = int(time.time())
    if abs(now - timestamp) > WEBHOOK_MAX_AGE_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="stale webhook timestamp",
        )

    expected_signature = compute_signature(raw_body, timestamp)
    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid webhook signature",
        )

    return timestamp


@router.post("/webhooks/payment-authorized")
async def payment_authorized_webhook(
    request: Request,
    x_provider_timestamp: str = Header(..., alias="X-Provider-Timestamp"),
    x_provider_signature: str = Header(..., alias="X-Provider-Signature"),
):
    raw_body = await request.body()
    if not raw_body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="request body is required",
        )

    verify_signature(raw_body, x_provider_signature, x_provider_timestamp)

    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="request body must be valid JSON",
        ) from exc

    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="request body must be a JSON object",
        )

    event_id_value: Any = parsed.get("event_id")
    event_id = (
        event_id_value
        if isinstance(event_id_value, str) and event_id_value.strip()
        else "unknown-event-id"
    )
    publish_raw_event(parsed, key=event_id)

    return {
        "status": "accepted",
        "event_id": event_id,
        "source": parsed.get("source", "unknown-source"),
    }
