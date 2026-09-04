import uuid
from datetime import datetime, date

from sqlalchemy import Column, String, DateTime, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import CHAR, TypeDecorator

from app.core.database import Base


class GUID(TypeDecorator):
    """Platform-independent UUID: native UUID on Postgres, CHAR(36) on SQLite."""
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID())
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return value if isinstance(value, uuid.UUID) else uuid.UUID(value)


class Gym(Base):
    __tablename__ = "gyms"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    subscription_status = Column(String, default="trial", nullable=False)
    platform_plan_id = Column(GUID(), ForeignKey("platform_plans.id"), nullable=True)
    razorpay_subscription_id = Column(String, nullable=True)
    trial_ends_at = Column(Date, nullable=True)
    current_period_end = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
