import uuid
from datetime import datetime

from sqlalchemy import Column, String, Numeric, Integer, DateTime

from app.core.database import Base
from app.models.gym import GUID


class PlatformPlan(Base):
    __tablename__ = "platform_plans"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, unique=True)
    price = Column(Numeric(10, 2), nullable=False)
    billing_interval = Column(String, nullable=False, default="monthly")
    member_limit = Column(Integer, nullable=True)  # None = unlimited
    razorpay_plan_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
