import uuid
from datetime import date
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, ConfigDict


class PlatformPlanResponse(BaseModel):
    id: uuid.UUID
    name: str
    price: Decimal
    billing_interval: str
    member_limit: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class SubscribeRequest(BaseModel):
    platform_plan_id: uuid.UUID


class SubscribeResponse(BaseModel):
    razorpay_subscription_id: str
    status: str
    checkout_url: Optional[str] = None


class BillingStatusResponse(BaseModel):
    plan_name: Optional[str] = None
    subscription_status: str
    trial_ends_at: Optional[date] = None
    current_period_end: Optional[date] = None
