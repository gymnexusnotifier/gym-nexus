import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, Text

from app.core.database import Base
from app.models.gym import GUID


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    gym_id = Column(GUID(), ForeignKey("gyms.id"), nullable=False, index=True)
    actor_id = Column(GUID(), ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
