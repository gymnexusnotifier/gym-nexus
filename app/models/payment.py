import uuid
from datetime import datetime, date

from sqlalchemy import Column, DateTime, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.gym import GUID


class Payment(Base):
    __tablename__ = "payments"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    gym_id = Column(GUID(), ForeignKey("gyms.id"), nullable=False)
    member_id = Column(GUID(), ForeignKey("members.id"), nullable=False)
    plan_id = Column(GUID(), ForeignKey("membership_plans.id"), nullable=True)
    amount = Column(Numeric(10, 2), nullable=False)
    payment_date = Column(Date, default=date.today, nullable=False)
    next_due_date = Column(Date, nullable=True)
    payment_method = Column(String, nullable=False, default="cash")
    transaction_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    member = relationship("Member")
    plan = relationship("MembershipPlan")
