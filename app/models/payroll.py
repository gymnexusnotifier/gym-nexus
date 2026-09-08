import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Numeric, Enum as SAEnum, Text

from app.core.database import Base
from app.models.enums import PayFrequency, PayrollStatus
from app.models.gym import GUID


class PayrollRecord(Base):
    __tablename__ = "payroll_records"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    gym_id = Column(GUID(), ForeignKey("gyms.id"), nullable=False, index=True)
    staff_id = Column(GUID(), ForeignKey("users.id"), nullable=False, index=True)
    pay_rate = Column(Numeric(10, 2), nullable=False)
    pay_frequency = Column(SAEnum(PayFrequency), nullable=False)
    pay_period_start = Column(Date, nullable=False)
    pay_period_end = Column(Date, nullable=False)
    days_in_period = Column(Numeric(8, 2), nullable=False)
    days_present = Column(Numeric(8, 2), nullable=False, default=0)
    leave_days_unpaid = Column(Numeric(8, 2), nullable=False, default=0)
    leave_deduction_amount = Column(Numeric(10, 2), nullable=False, default=0)
    leave_deduction_overridden = Column(Boolean, nullable=False, default=False)
    leave_deduction_override_note = Column(Text, nullable=True)
    other_deductions = Column(Numeric(10, 2), nullable=False, default=0)
    other_deductions_note = Column(Text, nullable=True)
    gross_amount = Column(Numeric(10, 2), nullable=False)
    net_amount = Column(Numeric(10, 2), nullable=False)
    status = Column(SAEnum(PayrollStatus), nullable=False, default=PayrollStatus.PENDING)
    released_date = Column(Date, nullable=True)
    payslip_sent_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)