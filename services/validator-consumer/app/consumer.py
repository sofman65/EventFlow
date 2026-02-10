import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from confluent_kafka import Consumer, Producer

BOOTSTRAP_SERVERS = "localhost:9092"
CONSUMER_GROUP_ID = "validator-service"
RAW_TOPIC = "events.raw.v1"
VALIDATED_TOPIC = "events.validated.v1"
DLQ_TOPIC = "events.dlq.v1"


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

    if not isinstance(event["payload"], dict):
        raise ValueError("payload must be an object")

    payload = event["payload"]
    if "order_id" not in payload:
        raise ValueError("payload.order_id is required")

    if "amount" not in payload:
        raise ValueError("payload.amount is required")

    amount = payload["amount"]
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise ValueError("payload.amount must be a number")
    if amount <= 0:
        raise ValueError("payload.amount must be greater than 0")


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
