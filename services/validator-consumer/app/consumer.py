import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

from confluent_kafka import Consumer, Producer

BOOTSTRAP_SERVERS = "localhost:9092"
CONSUMER_GROUP_ID = "validator-service"
RAW_TOPIC = "events.raw.v1"
VALIDATED_TOPIC = "events.validated.v1"
DLQ_TOPIC = "events.dlq.v1"
EXPECTED_EVENT_TYPE = "payment.authorized.v1"


consumer = Consumer(
    {
        "bootstrap.servers": BOOTSTRAP_SERVERS,
        "group.id": CONSUMER_GROUP_ID,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    }
)

producer = Producer(
    {
        "bootstrap.servers": BOOTSTRAP_SERVERS,
    }
)


def parse_event(msg) -> Dict[str, Any]:
    raw_value = msg.value()
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


def validate_event(event: Dict[str, Any]) -> None:
    required_fields = ("event_id", "event_type", "source", "timestamp", "payload")
    for field in required_fields:
        if field not in event:
            raise ValueError(f"missing required field: {field}")

    if not isinstance(event["event_id"], str) or not event["event_id"].strip():
        raise ValueError("event_id must be a non-empty string")

    if event["event_type"] != EXPECTED_EVENT_TYPE:
        raise ValueError(f"event_type must be {EXPECTED_EVENT_TYPE}")

    if not isinstance(event["payload"], dict):
        raise ValueError("payload must be an object")

    payload = event["payload"]
    required_payload_fields = (
        "payment_id",
        "order_id",
        "amount",
        "currency",
        "provider_auth_id",
    )
    for field in required_payload_fields:
        if field not in payload:
            raise ValueError(f"payload.{field} is required")

    for field in ("payment_id", "order_id", "provider_auth_id"):
        value = payload[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"payload.{field} must be a non-empty string")

    amount_raw = payload["amount"]
    if isinstance(amount_raw, bool):
        raise ValueError("payload.amount must be a number")

    try:
        amount = Decimal(str(amount_raw))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("payload.amount must be a number")

    if not amount.is_finite():
        raise ValueError("payload.amount must be a finite number")

    if amount <= 0:
        raise ValueError("payload.amount must be greater than 0")

    # Normalize for downstream contracts that expect JSON number semantics.
    payload["amount"] = float(amount)

    currency = payload["currency"]
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
        raise ValueError("payload.currency must be a 3-letter alphabetic code")
    if currency.upper() != currency:
        raise ValueError("payload.currency must be uppercase (for example, USD)")


def publish_json(topic: str, key: Optional[str], payload: Dict[str, Any]) -> None:
    producer.produce(
        topic=topic,
        key=key,
        value=json.dumps(payload, default=str),
    )
    in_flight = producer.flush(5.0)
    if in_flight > 0:
        raise RuntimeError(f"timed out publishing message to {topic}")


def build_dlq_payload(msg, error: Exception, event: Any) -> Dict[str, Any]:
    return {
        "failed_service": CONSUMER_GROUP_ID,
        "error_message": str(error),
        "source_topic": msg.topic(),
        "source_partition": msg.partition(),
        "source_offset": msg.offset(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
    }


consumer.subscribe([RAW_TOPIC])
print("Validator consumer started...")

try:
    while True:
        msg = consumer.poll(1.0)

        if msg is None:
            continue

        if msg.error():
            print(f"Consumer error: {msg.error()}")
            continue

        event: Any = None
        try:
            event = parse_event(msg)
            validate_event(event)

            event_id = str(event.get("event_id"))
            publish_json(VALIDATED_TOPIC, event_id, event)
            consumer.commit(message=msg, asynchronous=False)

            print(
                f"Validated event {event_id} from partition {msg.partition()} "
                f"offset {msg.offset()} -> {VALIDATED_TOPIC}"
            )
        except Exception as processing_error:
            if event is None:
                raw_value = msg.value()
                event = (
                    raw_value.decode("utf-8", errors="replace")
                    if isinstance(raw_value, (bytes, bytearray))
                    else str(raw_value)
                )

            dlq_key = event.get("event_id") if isinstance(event, dict) else None
            dlq_payload = build_dlq_payload(msg, processing_error, event)

            try:
                publish_json(DLQ_TOPIC, dlq_key, dlq_payload)
                consumer.commit(message=msg, asynchronous=False)
                print(
                    f"Sent failed event from partition {msg.partition()} "
                    f"offset {msg.offset()} -> {DLQ_TOPIC}: {processing_error}"
                )
            except Exception as dlq_error:
                print(
                    f"Failed to publish to {DLQ_TOPIC} for partition {msg.partition()} "
                    f"offset {msg.offset()}: {dlq_error}"
                )

except KeyboardInterrupt:
    print("\nStopping consumer")

finally:
    consumer.close()
    producer.flush(5.0)
