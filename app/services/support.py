import os
import uuid
from datetime import datetime

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.email import build_support_ticket_email, send_email
from app.core.storage import (
    SUPPORT_ALLOWED_TYPES,
    SUPPORT_MAX_ATTACHMENT_BYTES,
    save_support_attachment,
)
from app.models.enums import UserRole
from app.models.gym import Gym
from app.models.support import (
    SupportAttachment,
    SupportAuditEvent,
    SupportMessage,
    SupportTicket,
    TicketPriority,
    TicketStatus,
)
from app.models.user import User


ALLOWED_TRANSITIONS = {
    TicketStatus.OPEN: {TicketStatus.IN_PROGRESS, TicketStatus.CLOSED},
    TicketStatus.IN_PROGRESS: {TicketStatus.WAITING_FOR_GYM_OWNER, TicketStatus.RESOLVED, TicketStatus.CLOSED},
    TicketStatus.WAITING_FOR_GYM_OWNER: {TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, TicketStatus.CLOSED},
    TicketStatus.RESOLVED: {TicketStatus.CLOSED, TicketStatus.REOPENED},
    TicketStatus.CLOSED: {TicketStatus.REOPENED},
    TicketStatus.REOPENED: {TicketStatus.IN_PROGRESS, TicketStatus.CLOSED},
}


def add_audit(db: Session, ticket: SupportTicket, actor: User, event_type: str, details: str) -> None:
    db.add(SupportAuditEvent(ticket_id=ticket.id, actor_id=actor.id, event_type=event_type, details=details))


def notify_ticket_parties(db: Session, ticket: SupportTicket, actor: User, event: str) -> None:
    owner = db.query(User).filter(User.id == ticket.owner_id).first()
    admins = db.query(User).filter(User.role == UserRole.SUPER_ADMIN).all()
    recipients = admins if actor.role == UserRole.GYM_OWNER else ([owner] if owner else [])
    for recipient in recipients:
        if not recipient or not recipient.email:
            continue
        subject, body = build_support_ticket_email(ticket.ticket_code, ticket.subject, event, recipient.email)
        send_email(recipient.email, subject, body, is_html=True)


def create_ticket(db: Session, owner: User, subject: str, description: str, category: str, priority: str) -> SupportTicket:
    if not owner.gym_id:
        raise HTTPException(status_code=400, detail="User is not associated with a gym")
    try:
        selected_priority = TicketPriority(priority)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ticket priority")
    ticket = SupportTicket(
        gym_id=owner.gym_id, owner_id=owner.id, subject=subject.strip(), description=description.strip(),
        category=category.strip(), priority=selected_priority, status=TicketStatus.OPEN,
    )
    db.add(ticket)
    db.flush()
    message = SupportMessage(ticket_id=ticket.id, sender_id=owner.id, sender_role=owner.role.value, content=description.strip())
    db.add(message)
    db.flush()
    add_audit(db, ticket, owner, "ticket_created", f"Ticket {ticket.ticket_code} created")
    return ticket


def add_message(db: Session, ticket: SupportTicket, sender: User, content: str, is_internal: bool = False) -> SupportMessage:
    if sender.role != UserRole.SUPER_ADMIN and (sender.id != ticket.owner_id or is_internal):
        raise HTTPException(status_code=403, detail="You cannot add this message")
    if not content.strip():
        raise HTTPException(status_code=400, detail="Message content is required")
    message = SupportMessage(
        ticket_id=ticket.id, sender_id=sender.id, sender_role=sender.role.value,
        content=content.strip(), is_internal=1 if is_internal else 0,
    )
    db.add(message)
    db.flush()
    add_audit(db, ticket, sender, "internal_note" if is_internal else "message_added", content.strip()[:500])
    ticket.updated_at = datetime.utcnow()
    return message


def add_attachments(db: Session, ticket: SupportTicket, message: SupportMessage, sender: User, files: list[UploadFile]) -> None:
    for upload in files:
        if not upload or not upload.filename:
            continue
        if upload.content_type not in SUPPORT_ALLOWED_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported attachment type: {upload.filename}")
        content = upload.file.read(SUPPORT_MAX_ATTACHMENT_BYTES + 1)
        if len(content) > SUPPORT_MAX_ATTACHMENT_BYTES:
            raise HTTPException(status_code=400, detail=f"Attachment exceeds 8 MB: {upload.filename}")
        extension = os.path.splitext(upload.filename)[1].lstrip(".") or "bin"
        path = save_support_attachment(str(ticket.gym_id), str(ticket.id), content, upload.content_type, extension)
        db.add(SupportAttachment(
            ticket_id=ticket.id, message_id=message.id, uploaded_by_id=sender.id,
            original_name=upload.filename, storage_path=path,
            content_type=upload.content_type, size_bytes=len(content),
        ))
        add_audit(db, ticket, sender, "attachment_added", f"Attached {upload.filename}")


def change_status(db: Session, ticket: SupportTicket, actor: User, new_status: str, resolution: str = "") -> None:
    try:
        target = TicketStatus(new_status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ticket status")
    if target not in ALLOWED_TRANSITIONS.get(ticket.status, set()):
        raise HTTPException(status_code=400, detail=f"Invalid status transition: {ticket.status.value} to {target.value}")
    if target == TicketStatus.RESOLVED and not resolution.strip():
        raise HTTPException(status_code=400, detail="A resolution message is required")
    old_status = ticket.status
    ticket.status = target
    ticket.updated_at = datetime.utcnow()
    if target == TicketStatus.RESOLVED:
        ticket.resolved_at = datetime.utcnow()
        if resolution.strip():
            add_message(db, ticket, actor, resolution, is_internal=False)
    if target == TicketStatus.CLOSED:
        ticket.closed_at = datetime.utcnow()
    if target == TicketStatus.REOPENED:
        ticket.resolved_at = None
        ticket.closed_at = None
    add_audit(db, ticket, actor, "status_changed", f"{old_status.value} -> {target.value}")


def get_ticket_for_user(db: Session, ticket_id: uuid.UUID, user: User) -> SupportTicket | None:
    query = db.query(SupportTicket).filter(SupportTicket.id == ticket_id)
    if user.role != UserRole.SUPER_ADMIN:
        query = query.filter(SupportTicket.owner_id == user.id, SupportTicket.gym_id == user.gym_id)
    return query.first()