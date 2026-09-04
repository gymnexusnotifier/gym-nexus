import enum
import uuid
from datetime import datetime, date

from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Enum as SAEnum, Numeric, Integer
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.gym import GUID


class MemberStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    FROZEN = "frozen"


class MembershipPlan(Base):
    __tablename__ = "membership_plans"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    gym_id = Column(GUID(), ForeignKey("gyms.id"), nullable=False)
    name = Column(String, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    duration_days = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Member(Base):
    __tablename__ = "members"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    gym_id = Column(GUID(), ForeignKey("gyms.id"), nullable=False)
    plan_id = Column(GUID(), ForeignKey("membership_plans.id"), nullable=True)
    name = Column(String, nullable=False)
    contact = Column(String, nullable=True)
    email = Column(String, nullable=True)
    photo_path = Column(String, nullable=True)
    join_date = Column(Date, default=date.today, nullable=False)
    status = Column(SAEnum(MemberStatus), default=MemberStatus.ACTIVE, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    plan = relationship("MembershipPlan")
