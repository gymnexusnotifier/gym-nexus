import uuid
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role, require_permission, get_current_gym_id
from app.models.attendance import Attendance
from app.models.member import Member
from app.schemas.attendance import CheckInRequest, AttendanceResponse

router = APIRouter(prefix="/attendance", tags=["attendance"])

CHECKOUT_MIN_GAP_MINUTES = 15


def _minutes_since_checkin(check_in_time: str) -> Optional[float]:
    try:
        check_in_dt = datetime.strptime(f"{date.today()} {check_in_time}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return (datetime.now() - check_in_dt).total_seconds() / 60


def _auto_close_stale_attendance(db: Session, gym_id: uuid.UUID):
    open_records = db.query(Attendance).filter(
        Attendance.gym_id == gym_id,
        Attendance.check_out_time.is_(None),
    ).all()

    for record in open_records:
        if record.check_in_time is None:
            continue
        if record.date < date.today():
            record.check_out_time = "23:59:59"
            continue

        minutes_since = _minutes_since_checkin(record.check_in_time)
        if minutes_since is not None and minutes_since >= CHECKOUT_MIN_GAP_MINUTES:
            record.check_out_time = datetime.now().strftime("%H:%M:%S")

    if open_records:
        db.commit()


@router.post("/check-in", response_model=AttendanceResponse)
def check_in(
    payload: CheckInRequest,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_permission("attendance")),
):
    """
    Toggle endpoint: first call today for this member = check-in.
    Second call today = check-out. Further calls are a no-op.
    """
    member = db.query(Member).filter(Member.id == payload.member_id, Member.gym_id == gym_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found for this gym")

    _auto_close_stale_attendance(db, gym_id)

    today = date.today()
    now_str = datetime.now().strftime("%H:%M:%S")

    existing = db.query(Attendance).filter(
        Attendance.gym_id == gym_id,
        Attendance.member_id == member.id,
        Attendance.date == today,
    ).first()

    if existing is None:
        record = Attendance(
            gym_id=gym_id, member_id=member.id, date=today,
            check_in_time=now_str, status="present",
        )
        db.add(record)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.query(Attendance).filter(
                Attendance.gym_id == gym_id, Attendance.member_id == member.id, Attendance.date == today,
            ).first()
            return existing
        db.refresh(record)
        return record

    if existing.check_out_time is None:
        minutes_since = _minutes_since_checkin(existing.check_in_time)
        if minutes_since is not None and minutes_since < CHECKOUT_MIN_GAP_MINUTES:
            return existing
        existing.check_out_time = now_str
        db.commit()
        db.refresh(existing)
        return existing

    return existing


@router.get("", response_model=List[AttendanceResponse])
def list_attendance(
    member_id: Optional[uuid.UUID] = None,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_permission("attendance")),
):
    _auto_close_stale_attendance(db, gym_id)
    query = db.query(Attendance).filter(Attendance.gym_id == gym_id)
    if member_id:
        query = query.filter(Attendance.member_id == member_id)
    return query.order_by(Attendance.date.desc()).all()


@router.get("/today", response_model=List[AttendanceResponse])
def today_attendance(
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_permission("attendance")),
):
    _auto_close_stale_attendance(db, gym_id)
    today = date.today()
    return db.query(Attendance).filter(Attendance.gym_id == gym_id, Attendance.date == today).all()
