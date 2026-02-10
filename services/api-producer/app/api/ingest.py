from fastapi import APIRouter
from app.kafka.producer import publish_event
from app.schemas.events import PaymentAuthorizedEvent, PaymentAuthorizedPayload
from uuid import uuid4
from datetime import datetime, timezone

router = APIRouter()


@router.post("/ingest")
def ingest(payload: PaymentAuthorizedPayload):
    event = PaymentAuthorizedEvent(
        event_id=str(uuid4()),
        source="api-producer",
        timestamp=datetime.now(timezone.utc),
        payload=payload,
    )

    publish_event(event)

    return {
        "status": "accepted",
        "event_id": event.event_id,
    }
