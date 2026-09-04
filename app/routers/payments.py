import uuid
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role, require_permission, get_current_gym_id
from app.models.payment import Payment
from app.models.member import Member, MemberStatus, MembershipPlan
from app.models.gym import Gym
from app.schemas.payment import PaymentCreate, PaymentResponse, UpcomingRenewal
from app.services.receipt import generate_receipt_pdf
from app.core.email import build_payment_confirmation_email, send_email

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("", response_model=PaymentResponse)
def create_payment(
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_permission("payments")),
):
    if payload.payment_method not in {"cash", "upi", "card", "bank_transfer"}:
        raise HTTPException(status_code=400, detail="Invalid payment method")
    if payload.payment_method == "upi" and not (payload.transaction_id or "").strip():
        raise HTTPException(status_code=400, detail="transaction_id is required for UPI payments")
    member = db.query(Member).filter(Member.id == payload.member_id, Member.gym_id == gym_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    gym = db.query(Gym).filter(Gym.id == gym_id).first()

    plan = None
    if payload.plan_id:
        plan = db.query(MembershipPlan).filter(
            MembershipPlan.id == payload.plan_id, MembershipPlan.gym_id == gym_id
        ).first()
        if not plan:
            raise HTTPException(status_code=400, detail="Invalid plan_id for this gym")

    today = date.today()
    next_due = today + timedelta(days=plan.duration_days) if plan else None

    payment = Payment(
        gym_id=gym_id,
        member_id=member.id,
        plan_id=plan.id if plan else None,
        amount=payload.amount,
        payment_date=today,
        next_due_date=next_due,
        payment_method=payload.payment_method,
        transaction_id=payload.transaction_id.strip() if payload.transaction_id else None,
    )
    db.add(payment)

    member.status = MemberStatus.ACTIVE
    if plan:
        member.plan_id = plan.id

    db.commit()
    db.refresh(payment)
    if member.email:
        subject, body = build_payment_confirmation_email(
            gym.name if gym else "Your gym",
            member.name,
            payment.amount,
            payment.payment_date,
            plan.name if plan else "General payment",
            payment.next_due_date,
            payment.payment_method,
            payment.transaction_id,
        )
        receipt = generate_receipt_pdf(gym.name if gym else "Gym", payment, member.name, plan.name if plan else "General payment")
        send_email(member.email, subject, body, is_html=True, attachments=[(f"receipt_{str(payment.id)[:8]}.pdf", receipt.read(), "application/pdf")])
    return payment


@router.get("", response_model=List[PaymentResponse])
def list_payments(
    member_id: Optional[uuid.UUID] = None,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_permission("payments")),
):
    query = db.query(Payment).filter(Payment.gym_id == gym_id)
    if member_id:
        query = query.filter(Payment.member_id == member_id)
    return query.order_by(Payment.payment_date.desc()).all()


@router.get("/upcoming-renewals", response_model=List[UpcomingRenewal])
def upcoming_renewals(
    days: int = 7,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_permission("payments")),
):
    cutoff = date.today() + timedelta(days=days)

    results = (
        db.query(Payment, Member)
        .join(Member, Member.id == Payment.member_id)
        .filter(
            Payment.gym_id == gym_id,
            Payment.next_due_date.isnot(None),
            Payment.next_due_date <= cutoff,
            Payment.next_due_date >= date.today(),
        )
        .order_by(Payment.next_due_date.asc())
        .all()
    )

    return [
        UpcomingRenewal(member_id=member.id, member_name=member.name, next_due_date=payment.next_due_date)
        for payment, member in results
    ]


def _get_payment_or_404(payment_id: uuid.UUID, gym_id: uuid.UUID, db: Session) -> Payment:
    payment = db.query(Payment).filter(Payment.id == payment_id, Payment.gym_id == gym_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


@router.get("/{payment_id}/receipt")
def get_receipt(
    payment_id: uuid.UUID,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_permission("payments")),
):
    payment = _get_payment_or_404(payment_id, gym_id, db)
    member = db.query(Member).filter(Member.id == payment.member_id).first()
    gym = db.query(Gym).filter(Gym.id == gym_id).first()
    plan = (
        db.query(MembershipPlan).filter(MembershipPlan.id == payment.plan_id).first()
        if payment.plan_id else None
    )

    buffer = generate_receipt_pdf(
        gym_name=gym.name if gym else "Gym",
        payment=payment,
        member_name=member.name if member else "Unknown",
        plan_name=plan.name if plan else "N/A",
    )

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=receipt_{str(payment.id)[:8]}.pdf"},
    )
