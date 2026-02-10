from fastapi import APIRouter
from app.kafka.producer import publish_event
from app.schemas.events import RawEvent
from uuid import uuid4
from datetime import datetime

router = APIRouter()


@router.post("/ingest")
def ingest(payload: dict):
    event = RawEvent(
        event_id=str(uuid4()),
        event_type="ingest",
        source="api-producer",
        timestamp=datetime.utcnow(),
        payload=payload,
    )

    publish_event(event)

    return {
        "status": "accepted",
        "event_id": event.event_id,
    }
