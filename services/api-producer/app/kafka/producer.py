import json
from confluent_kafka import Producer
from app.schemas.events import RawEvent

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


def publish_event(event: RawEvent):
    producer.produce(
        topic=TOPIC,
        key=event.event_id,
        value=json.dumps(event.dict(), default=str),
        on_delivery=delivery_report,
    )
    producer.poll(0)
