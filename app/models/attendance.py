import uuid
from datetime import datetime, date

from sqlalchemy import Column, DateTime, Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.gym import GUID


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("gym_id", "member_id", "date", name="uq_attendance_gym_member_date"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    gym_id = Column(GUID(), ForeignKey("gyms.id"), nullable=False)
    member_id = Column(GUID(), ForeignKey("members.id"), nullable=False)
    date = Column(Date, default=date.today, nullable=False)
    check_in_time = Column(String, nullable=False)
    check_out_time = Column(String, nullable=True)
    status = Column(String, default="present", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    member = relationship("Member")
