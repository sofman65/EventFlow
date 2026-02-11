import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from confluent_kafka import Consumer
from prometheus_client import Counter, Histogram, start_http_server

BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
GROUP_ID = os.getenv("ANALYTICS_GROUP_ID", "analytics-service")
TOPIC = os.getenv("ANALYTICS_TOPIC", "events.validated.v1")
METRICS_PORT = int(os.getenv("ANALYTICS_METRICS_PORT", "8002"))

ANALYTICS_TOTAL_PROCESSED = Counter(
    "eventflow_analytics_total_processed_total",
    "Total validated events processed by analytics consumer.",
)
ANALYTICS_BY_EVENT_TYPE = Counter(
    "eventflow_analytics_by_event_type_total",
    "Validated events processed by analytics consumer by event type.",
    ["event_type"],
)
ANALYTICS_BY_PARTITION = Counter(
    "eventflow_analytics_by_partition_total",
    "Validated events processed by analytics consumer by partition.",
    ["partition"],
)
ANALYTICS_PROCESSING_ERRORS = Counter(
    "eventflow_analytics_processing_errors_total",
    "Total processing errors in analytics consumer.",
)
ANALYTICS_EVENT_AGE_MS = Histogram(
    "eventflow_analytics_event_age_ms",
    "Age (milliseconds) of event when processed by analytics consumer.",
    buckets=(
        1,
        5,
        10,
        25,
        50,
        100,
        250,
        500,
        1000,
        2500,
        5000,
        10000,
        30000,
        60000,
        300000,
    ),
)
ANALYTICS_PROCESSING_LATENCY_SECONDS = Histogram(
    "eventflow_analytics_processing_latency_seconds",
    "Analytics consumer processing latency per message.",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)


def parse_event(raw_value: Optional[bytes]) -> Dict[str, Any]:
    if raw_value is None:
        raise ValueError("message value is empty")

    raw_text = (
        raw_value.decode("utf-8", errors="replace")
        if isinstance(raw_value, (bytes, bytearray))
        else str(raw_value)
    )
    event = json.loads(raw_text)
    if not isinstance(event, dict):
        raise ValueError("event payload must be a JSON object")
    return event


def parse_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None

    candidate = value.strip()
    # Accept both ISO-8601 and older "YYYY-MM-DD HH:MM:SS.ssssss" format.
    if " " in candidate and "T" not in candidate:
        candidate = candidate.replace(" ", "T", 1)
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def observe_event_age_ms(event: Dict[str, Any]) -> None:
    timestamp = parse_timestamp(event.get("timestamp"))
    if timestamp is None:
        return

    age_ms = (datetime.now(timezone.utc) - timestamp).total_seconds() * 1000
    if age_ms >= 0:
        ANALYTICS_EVENT_AGE_MS.observe(age_ms)


consumer = Consumer(
    {
        "bootstrap.servers": BOOTSTRAP_SERVERS,
        "group.id": GROUP_ID,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    }
)

consumer.subscribe([TOPIC])
start_http_server(METRICS_PORT)

print("Analytics consumer started...")
print(f"Analytics metrics exposed at http://localhost:{METRICS_PORT}/metrics")

try:
    while True:
        msg = consumer.poll(1.0)
        if msg is None:
            continue

        if msg.error():
            ANALYTICS_PROCESSING_ERRORS.inc()
            print(f"Kafka error: {msg.error()}")
            continue

        started = time.perf_counter()
        try:
            event = parse_event(msg.value())
            event_type = str(event.get("event_type", "unknown"))
            partition = str(msg.partition())

            ANALYTICS_TOTAL_PROCESSED.inc()
            ANALYTICS_BY_EVENT_TYPE.labels(event_type=event_type).inc()
            ANALYTICS_BY_PARTITION.labels(partition=partition).inc()
            observe_event_age_ms(event)

            consumer.commit(message=msg, asynchronous=False)

            print(
                f"Analytics processed event {event.get('event_id', 'unknown')} "
                f"type {event_type} from partition {partition} offset {msg.offset()}"
            )
        except Exception as processing_error:
            ANALYTICS_PROCESSING_ERRORS.inc()
            print(
                f"Analytics failed for partition {msg.partition()} "
                f"offset {msg.offset()}: {processing_error}"
            )
        finally:
            ANALYTICS_PROCESSING_LATENCY_SECONDS.observe(time.perf_counter() - started)

except KeyboardInterrupt:
    print("\nStopping analytics consumer")

finally:
    consumer.close()
