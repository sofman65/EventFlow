from confluent_kafka import Consumer
import json

consumer = Consumer(
    {
        "bootstrap.servers": "localhost:9092",
        "group.id": "validator-service",
        "auto.offset.reset": "earliest",
    }
)

consumer.subscribe(["events.raw.v1"])

print("Validator consumer started...")

while True:
    msg = consumer.poll(1.0)

    if msg is None:
        continue

    if msg.error():
        print(f"Consumer error: {msg.error()}")
        continue

    event = json.loads(msg.value())
    print(f"Consumed event {event['event_id']} from partition {msg.partition()}")

    consumer.commit()
