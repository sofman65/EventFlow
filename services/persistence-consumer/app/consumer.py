import json
import sqlite3
from datetime import datetime, timezone
from confluent_kafka import Consumer

BOOTSTRAP_SERVERS = "localhost:9092"
GROUP_ID = "persistence-service"
TOPIC = "events.validated.v1"  # or events.validated.v1

DB_PATH = "events.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            source TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            payload TEXT NOT NULL,
            stored_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def store_event(event: dict):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT OR IGNORE INTO events
        (event_id, event_type, source, timestamp, payload, stored_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            event["event_id"],
            event["event_type"],
            event["source"],
            event["timestamp"],
            json.dumps(event["payload"]),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


consumer = Consumer(
    {
        "bootstrap.servers": BOOTSTRAP_SERVERS,
        "group.id": GROUP_ID,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    }
)

init_db()
consumer.subscribe([TOPIC])

print("Persistence consumer started...")

try:
    while True:
        msg = consumer.poll(1.0)

        if msg is None:
            continue

        if msg.error():
            print(f"Kafka error: {msg.error()}")
            continue

        event = json.loads(msg.value())

        store_event(event)
        consumer.commit(message=msg, asynchronous=False)

        print(
            f"Stored event {event['event_id']} "
            f"from partition {msg.partition()} offset {msg.offset()}"
        )

except KeyboardInterrupt:
    print("\nStopping persistence consumer")

finally:
    consumer.close()
