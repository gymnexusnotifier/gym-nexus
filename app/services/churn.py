"""
Rule-based churn risk scoring.

Deliberately transparent (not a black box) - each result comes with a
plain-English reason, so this is defensible as a marketable "AI Insight"
feature from day one. Once enough historical renew/churn data exists
across gyms, this can be swapped for a trained scikit-learn classifier
without changing anything in the API layer that calls it.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models.member import Member
from app.models.attendance import Attendance
from app.models.payment import Payment


def _risk(level: str, reason: str) -> dict:
    return {"risk_level": level, "reason": reason}


def compute_churn_risk(db: Session, gym_id, member: Member) -> dict:
    today = date.today()

    last_visit_row = (
        db.query(Attendance.date)
        .filter(Attendance.gym_id == gym_id, Attendance.member_id == member.id)
        .order_by(Attendance.date.desc())
        .first()
    )
    last_visit_date = last_visit_row[0] if last_visit_row else None
    days_since_visit = (today - last_visit_date).days if last_visit_date else None

    latest_payment = (
        db.query(Payment)
        .filter(
            Payment.gym_id == gym_id,
            Payment.member_id == member.id,
            Payment.next_due_date.isnot(None),
        )
        .order_by(Payment.next_due_date.desc())
        .first()
    )
    days_until_expiry = (latest_payment.next_due_date - today).days if latest_payment else None
    days_since_join = (today - member.join_date).days

    # Never checked in at all
    if days_since_visit is None:
        if days_since_join >= 14:
            return _risk("high", f"No check-ins recorded since joining {days_since_join} days ago.")
        return _risk("low", "Recently joined, no attendance history yet.")

    if days_since_visit >= 10:
        if days_until_expiry is not None and days_until_expiry <= 14:
            return _risk(
                "high",
                f"No visit in {days_since_visit} days and membership due within "
                f"{max(days_until_expiry, 0)} days.",
            )
        return _risk("medium", f"No visit in {days_since_visit} days.")

    if days_since_visit >= 5:
        if days_until_expiry is not None and days_until_expiry <= 14:
            return _risk(
                "medium",
                f"No visit in {days_since_visit} days and membership due within {days_until_expiry} days.",
            )
        return _risk("low", f"Visited {days_since_visit} day(s) ago.")

    return _risk("low", f"Visited recently ({days_since_visit} day(s) ago).")
