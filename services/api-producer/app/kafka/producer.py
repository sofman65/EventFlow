import json
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


def publish_event(event: PaymentAuthorizedEvent):
    producer.produce(
        topic=TOPIC,
        key=event.event_id,
        value=json.dumps(event.model_dump(mode="json")),
        on_delivery=delivery_report,
    )
    producer.poll(0)
