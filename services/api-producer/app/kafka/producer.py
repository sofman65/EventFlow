import json
from typing import Optional

from confluent_kafka import Producer
from app.schemas.events import PaymentAuthorizedEvent

producer = Producer(
    {
        "bootstrap.servers": "localhost:9092",
        "linger.ms": 5,
    }
)

TOPIC = "events.raw.v1"


def delivery_report(err, msg):
    if err:
        print(f"Delivery failed: {err}")
    else:
        print(
            f"Produced event to {msg.topic()} "
            f"[partition {msg.partition()}] "
            f"@ offset {msg.offset()}"
        )


def publish_raw_event(payload: dict, key: Optional[str] = None):
    producer.produce(
        topic=TOPIC,
        key=key,
        value=json.dumps(payload, default=str),
        on_delivery=delivery_report,
    )
    producer.poll(0)


def publish_event(event: PaymentAuthorizedEvent):
    publish_raw_event(
        payload=event.model_dump(mode="json"),
        key=event.event_id,
    )
