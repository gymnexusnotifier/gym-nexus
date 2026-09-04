import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.gym import GUID


class GymClass(Base):
    __tablename__ = "gym_classes"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    gym_id = Column(GUID(), ForeignKey("gyms.id"), nullable=False)
    trainer_id = Column(GUID(), ForeignKey("users.id"), nullable=True)
    name = Column(String, nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday .. 6=Sunday
    start_time = Column(String, nullable=False)    # "HH:MM"
    duration_minutes = Column(Integer, nullable=False, default=60)
    capacity = Column(Integer, nullable=False, default=10)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    trainer = relationship("User")


class ClassBooking(Base):
    __tablename__ = "class_bookings"
    __table_args__ = (
        UniqueConstraint("class_id", "member_id", name="uq_booking_class_member"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    gym_id = Column(GUID(), ForeignKey("gyms.id"), nullable=False)
    class_id = Column(GUID(), ForeignKey("gym_classes.id"), nullable=False)
    member_id = Column(GUID(), ForeignKey("members.id"), nullable=False)
    booked_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    gym_class = relationship("GymClass")
    member = relationship("Member")
