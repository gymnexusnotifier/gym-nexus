import uuid
from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, Enum as SAEnum, ForeignKey, Numeric, Text

from app.core.database import Base
from app.models.enums import LeaveType
from app.models.gym import GUID


class StaffLeave(Base):
    __tablename__ = "staff_leaves"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    gym_id = Column(GUID(), ForeignKey("gyms.id"), nullable=False, index=True)
    staff_id = Column(GUID(), ForeignKey("users.id"), nullable=False, index=True)
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False, index=True)
    leave_type = Column(SAEnum(LeaveType), nullable=False, default=LeaveType.UNPAID)
    day_fraction = Column(Numeric(3, 2), nullable=False, default=1)
    note = Column(Text, nullable=True)
    deleted_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)