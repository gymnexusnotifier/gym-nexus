import uuid
from datetime import date, datetime

from sqlalchemy import Column, String, Date, DateTime, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.gym import GUID

import enum


class InquiryStatus(str, enum.Enum):
    NEW = "new"
    SCHEDULED = "scheduled"
    CONVERTED = "converted"
    LOST = "lost"


class Inquiry(Base):
    __tablename__ = "inquiries"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    gym_id = Column(GUID(), ForeignKey("gyms.id"), nullable=False)
    name = Column(String, nullable=False)
    contact = Column(String, nullable=True)
    email = Column(String, nullable=True)
    source = Column(String, nullable=True)
    fitness_goal = Column(String, nullable=True)
    preferred_time = Column(String, nullable=True)
    age = Column(String, nullable=True)
    occupation = Column(String, nullable=True)
    interested_plan_id = Column(GUID(), ForeignKey("membership_plans.id"), nullable=True)
    assigned_staff_id = Column(GUID(), ForeignKey("users.id"), nullable=True)
    status = Column(SAEnum(InquiryStatus), default=InquiryStatus.NEW, nullable=False)
    next_followup = Column(Date, nullable=True)
    last_reminded = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    followups = relationship("FollowUp", back_populates="inquiry", cascade="all, delete-orphan")
    plan = relationship("MembershipPlan")


class FollowUp(Base):
    __tablename__ = "followups"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    inquiry_id = Column(GUID(), ForeignKey("inquiries.id"), nullable=False)
    staff_id = Column(GUID(), ForeignKey("users.id"), nullable=True)
    note = Column(Text, nullable=True)
    outcome = Column(String, nullable=True)
    next_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    inquiry = relationship("Inquiry", back_populates="followups")
