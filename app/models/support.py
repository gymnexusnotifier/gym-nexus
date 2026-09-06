import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text

from app.core.database import Base
from app.models.gym import GUID


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_GYM_OWNER = "waiting_for_gym_owner"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"


class TicketPriority(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    ticket_code = Column(String(24), unique=True, nullable=False, index=True,
                         default=lambda: f"TKT-{uuid.uuid4().hex[:12].upper()}")
    gym_id = Column(GUID(), ForeignKey("gyms.id"), nullable=False, index=True)
    owner_id = Column(GUID(), ForeignKey("users.id"), nullable=False, index=True)
    subject = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(80), nullable=False)
    priority = Column(SAEnum(TicketPriority), nullable=False, default=TicketPriority.NORMAL)
    status = Column(SAEnum(TicketStatus), nullable=False, default=TicketStatus.OPEN, index=True)
    assigned_to_id = Column(GUID(), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(GUID(), ForeignKey("support_tickets.id"), nullable=False, index=True)
    sender_id = Column(GUID(), ForeignKey("users.id"), nullable=False, index=True)
    sender_role = Column(String(30), nullable=False)
    content = Column(Text, nullable=False)
    is_internal = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class SupportAttachment(Base):
    __tablename__ = "support_attachments"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(GUID(), ForeignKey("support_tickets.id"), nullable=False, index=True)
    message_id = Column(GUID(), ForeignKey("support_messages.id"), nullable=False, index=True)
    uploaded_by_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    original_name = Column(String(255), nullable=False)
    storage_path = Column(String(500), nullable=False)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SupportAuditEvent(Base):
    __tablename__ = "support_audit_events"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(GUID(), ForeignKey("support_tickets.id"), nullable=False, index=True)
    actor_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    event_type = Column(String(60), nullable=False)
    details = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)