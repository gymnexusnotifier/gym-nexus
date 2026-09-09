import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Enum as SAEnum, Numeric
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.gym import GUID
from app.models.enums import UserRole, PayFrequency


class User(Base):
    __tablename__ = "users"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    gym_id = Column(GUID(), ForeignKey("gyms.id"), nullable=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(SAEnum(UserRole), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    salary_rate = Column(Numeric(10, 2), nullable=True)
    salary_frequency = Column(SAEnum(PayFrequency), nullable=True)
    salary_start_date = Column(Date, nullable=True)

    gym = relationship("Gym")
