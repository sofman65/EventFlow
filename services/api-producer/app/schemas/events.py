from pydantic import BaseModel
from datetime import datetime
from typing import Dict, Any


class RawEvent(BaseModel):
    event_id: str
    event_type: str
    source: str
    timestamp: datetime
    payload: Dict[str, Any]
