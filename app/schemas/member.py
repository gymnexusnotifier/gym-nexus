import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr


class PlanCreate(BaseModel):
    name: str
    price: Decimal
    duration_days: int


class PlanResponse(BaseModel):
    id: uuid.UUID
    name: str
    price: Decimal
    duration_days: int

    model_config = ConfigDict(from_attributes=True)


class MemberCreate(BaseModel):
    name: str
    contact: Optional[str] = None
    email: Optional[EmailStr] = None
    plan_id: Optional[uuid.UUID] = None


class MemberUpdate(BaseModel):
    name: Optional[str] = None
    contact: Optional[str] = None
    email: Optional[EmailStr] = None
    plan_id: Optional[uuid.UUID] = None
    status: Optional[str] = None


class MemberResponse(BaseModel):
    id: uuid.UUID
    name: str
    contact: Optional[str] = None
    email: Optional[str] = None
    plan_id: Optional[uuid.UUID] = None
    join_date: date
    status: str

    model_config = ConfigDict(from_attributes=True)
