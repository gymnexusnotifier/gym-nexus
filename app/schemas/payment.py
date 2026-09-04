import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PaymentCreate(BaseModel):
    member_id: uuid.UUID
    plan_id: Optional[uuid.UUID] = None
    amount: Decimal
    payment_method: str = "cash"
    transaction_id: Optional[str] = None


class PaymentResponse(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    plan_id: Optional[uuid.UUID] = None
    amount: Decimal
    payment_date: date
    next_due_date: Optional[date] = None
    payment_method: str
    transaction_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UpcomingRenewal(BaseModel):
    member_id: uuid.UUID
    member_name: str
    next_due_date: date
