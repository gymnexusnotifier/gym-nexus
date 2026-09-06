import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.models.enums import UserRole
from app.models.support import SupportAttachment, SupportMessage, SupportTicket, TicketStatus
from app.models.user import User
from app.services.support import add_attachments, add_message, change_status, create_ticket, get_ticket_for_user, notify_ticket_parties

router = APIRouter(prefix="/support", tags=["support"])


class TicketCreateRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10000)
    category: str = Field(min_length=1, max_length=80)
    priority: str = "normal"


class TicketStatusRequest(BaseModel):
    status: str
    resolution: str = ""


def _ticket_payload(db: Session, ticket: SupportTicket, include_internal: bool = False) -> dict:
    messages = db.query(SupportMessage).filter(SupportMessage.ticket_id == ticket.id).order_by(SupportMessage.created_at.asc()).all()
    if not include_internal:
        messages = [message for message in messages if not message.is_internal]
    attachments = db.query(SupportAttachment).filter(SupportAttachment.ticket_id == ticket.id).all()
    return {
        "id": str(ticket.id), "ticket_code": ticket.ticket_code, "subject": ticket.subject,
        "description": ticket.description, "category": ticket.category, "priority": ticket.priority.value,
        "status": ticket.status.value, "gym_id": str(ticket.gym_id), "owner_id": str(ticket.owner_id),
        "created_at": ticket.created_at, "updated_at": ticket.updated_at,
        "resolved_at": ticket.resolved_at, "closed_at": ticket.closed_at,
        "messages": [{"id": str(item.id), "sender_id": str(item.sender_id), "sender_role": item.sender_role, "content": item.content, "created_at": item.created_at} for item in messages],
        "attachments": [{"id": str(item.id), "message_id": str(item.message_id), "name": item.original_name, "content_type": item.content_type, "size_bytes": item.size_bytes} for item in attachments],
    }


@router.get("/tickets")
def list_tickets(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(SupportTicket).order_by(SupportTicket.updated_at.desc())
    if user.role != UserRole.SUPER_ADMIN:
        query = query.filter(SupportTicket.owner_id == user.id, SupportTicket.gym_id == user.gym_id)
    return [_ticket_payload(db, ticket, user.role == UserRole.SUPER_ADMIN) for ticket in query.all()]


@router.post("/tickets", status_code=201)
def create_ticket_api(payload: TicketCreateRequest, db: Session = Depends(get_db), user: User = Depends(require_role("gym_owner"))):
    ticket = create_ticket(db, user, payload.subject, payload.description, payload.category, payload.priority)
    db.commit()
    db.refresh(ticket)
    notify_ticket_parties(db, ticket, user, "New ticket created")
    return _ticket_payload(db, ticket)


@router.get("/tickets/{ticket_id}")
def get_ticket_api(ticket_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ticket = get_ticket_for_user(db, ticket_id, user)
    if not ticket:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _ticket_payload(db, ticket, user.role == UserRole.SUPER_ADMIN)


@router.post("/tickets/{ticket_id}/messages")
async def add_ticket_message_api(ticket_id: uuid.UUID, content: str = Form(...), attachments: list[UploadFile] = File(default=[]), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ticket = get_ticket_for_user(db, ticket_id, user)
    if not ticket:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Ticket not found")
    message = add_message(db, ticket, user, content)
    add_attachments(db, ticket, message, user, attachments)
    db.commit()
    notify_ticket_parties(db, ticket, user, "New reply added")
    return _ticket_payload(db, ticket, user.role == UserRole.SUPER_ADMIN)


@router.patch("/tickets/{ticket_id}/status")
def update_ticket_status_api(ticket_id: uuid.UUID, payload: TicketStatusRequest, db: Session = Depends(get_db), user: User = Depends(require_role("super_admin"))):
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Ticket not found")
    change_status(db, ticket, user, payload.status, payload.resolution)
    db.commit()
    notify_ticket_parties(db, ticket, user, f"Ticket status changed to {payload.status.replace('_', ' ')}")
    return _ticket_payload(db, ticket, True)