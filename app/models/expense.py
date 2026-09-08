import uuid
from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Numeric, Enum as SAEnum, Text

from app.core.database import Base
from app.models.enums import ExpenseCategory
from app.models.gym import GUID


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    gym_id = Column(GUID(), ForeignKey("gyms.id"), nullable=False, index=True)
    category = Column(SAEnum(ExpenseCategory), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    date = Column(Date, default=date.today, nullable=False, index=True)
    description = Column(Text, nullable=False)
    receipt_url = Column(Text, nullable=True)
    created_by = Column(GUID(), ForeignKey("users.id"), nullable=False)
    deleted_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)