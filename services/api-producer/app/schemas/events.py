from pydantic import BaseModel, Field, ConfigDict, field_serializer
from datetime import datetime
from typing import Literal
from decimal import Decimal


class PaymentAuthorizedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_id: str = Field(..., min_length=1)
    order_id: str = Field(..., min_length=1)
    amount: Decimal = Field(..., gt=0)
    currency: str = Field(..., pattern="^[A-Z]{3}$")
    provider_auth_id: str = Field(..., min_length=1)

    @field_serializer("amount")
    def serialize_amount(self, amount: Decimal) -> float:
        return float(amount)


class PaymentAuthorizedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., min_length=1)
    event_type: Literal["payment.authorized.v1"] = "payment.authorized.v1"
    schema_version: Literal[1] = 1
    source: str = Field(..., min_length=1)
    timestamp: datetime
    payload: PaymentAuthorizedPayload
