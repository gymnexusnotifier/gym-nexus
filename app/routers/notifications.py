import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permission, get_current_gym_id
from app.core.email import send_email
from app.models.member import Member, MemberStatus
from app.models.payment import Payment
from app.models.gym import Gym
from app.services.churn import compute_churn_risk
from app.schemas.notification import NotificationResult

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("/renewal-reminders", response_model=NotificationResult)
def send_renewal_reminders(
    days: int = 7,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_permission("notifications")),
):
    gym = db.query(Gym).filter(Gym.id == gym_id).first()
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
        .all()
    )

    sent, skipped, failed = 0, 0, 0
    for payment, member in results:
        if not member.email:
            skipped += 1
            continue

        subject = f"Your membership at {gym.name} is renewing soon"
        body = (
            f"Hi {member.name},\n\n"
            f"Just a reminder that your membership at {gym.name} is due for renewal "
            f"on {payment.next_due_date.isoformat()}. Please visit the front desk to renew.\n\n"
            f"- {gym.name}"
        )
        if send_email(member.email, subject, body):
            sent += 1
        else:
            failed += 1

    return NotificationResult(sent=sent, skipped_no_email=skipped, failed=failed)


@router.post("/inactivity-nudges", response_model=NotificationResult)
def send_inactivity_nudges(
    min_level: str = "medium",
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_permission("notifications")),
):
    gym = db.query(Gym).filter(Gym.id == gym_id).first()
    level_order = {"low": 0, "medium": 1, "high": 2}
    threshold = level_order.get(min_level, 1)

    members = db.query(Member).filter(
        Member.gym_id == gym_id, Member.status == MemberStatus.ACTIVE
    ).all()

    sent, skipped, failed = 0, 0, 0
    for member in members:
        risk = compute_churn_risk(db, gym_id, member)
        if level_order.get(risk["risk_level"], 0) < threshold:
            continue

        if not member.email:
            skipped += 1
            continue

        subject = f"We miss you at {gym.name}!"
        body = (
            f"Hi {member.name},\n\n"
            f"We noticed you haven't been in for a while. {risk['reason']}\n"
            f"Come back and see us soon - we'd love to have you back on track!\n\n"
            f"- {gym.name}"
        )
        if send_email(member.email, subject, body):
            sent += 1
        else:
            failed += 1

    return NotificationResult(sent=sent, skipped_no_email=skipped, failed=failed)
