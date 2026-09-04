import uuid
from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permission, get_current_gym_id
from app.models.member import Member, MemberStatus
from app.models.attendance import Attendance
from app.models.payment import Payment
from app.schemas.dashboard import DashboardSummary, PeakHourEntry

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_permission("dashboard")),
):
    today = date.today()

    today_checkins = db.query(Attendance).filter(
        Attendance.gym_id == gym_id, Attendance.date == today
    ).count()

    currently_in_gym = db.query(Attendance).filter(
        Attendance.gym_id == gym_id, Attendance.date == today, Attendance.check_out_time.is_(None)
    ).count()

    active_members = db.query(Member).filter(
        Member.gym_id == gym_id, Member.status == MemberStatus.ACTIVE
    ).count()

    expired_members = db.query(Member).filter(
        Member.gym_id == gym_id, Member.status == MemberStatus.EXPIRED
    ).count()

    frozen_members = db.query(Member).filter(
        Member.gym_id == gym_id, Member.status == MemberStatus.FROZEN
    ).count()

    month_start = today.replace(day=1)
    monthly_revenue = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.gym_id == gym_id, Payment.payment_date >= month_start
    ).scalar()

    return DashboardSummary(
        today_checkins=today_checkins,
        currently_in_gym=currently_in_gym,
        active_members=active_members,
        expired_members=expired_members,
        frozen_members=frozen_members,
        monthly_revenue=monthly_revenue,
    )


@router.get("/peak-hours", response_model=List[PeakHourEntry])
def peak_hours(
    days: int = 30,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_permission("dashboard")),
):
    cutoff = date.today() - timedelta(days=days)
    records = db.query(Attendance.check_in_time).filter(
        Attendance.gym_id == gym_id, Attendance.date >= cutoff
    ).all()

    hour_counts = {}
    for (time_str,) in records:
        hour = int(time_str.split(":")[0])
        hour_counts[hour] = hour_counts.get(hour, 0) + 1

    return [
        PeakHourEntry(hour=hour, checkins=count)
        for hour, count in sorted(hour_counts.items())
    ]
