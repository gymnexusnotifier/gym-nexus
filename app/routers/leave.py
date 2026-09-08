import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_gym_id, require_role
from app.models.enums import LeaveType, UserRole
from app.models.staff_leave import StaffLeave
from app.models.user import User
from app.schemas.staff_leave import StaffLeaveCreate, StaffLeaveResponse

router = APIRouter(prefix="/leave", tags=["leave"])


def _staff_or_404(db: Session, staff_id: uuid.UUID, gym_id: uuid.UUID) -> User:
    staff = db.query(User).filter(
        User.id == staff_id, User.gym_id == gym_id,
        User.role.in_([UserRole.STAFF, UserRole.TRAINER]),
    ).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")
    return staff


def count_unpaid_leave_days(db: Session, gym_id: uuid.UUID, staff_id: uuid.UUID, period_start: date, period_end: date) -> Decimal:
    """Count only the inclusive overlap with the pay period, including half-days."""
    if period_end < period_start:
        return Decimal("0")
    records = db.query(StaffLeave).filter(
        StaffLeave.gym_id == gym_id,
        StaffLeave.staff_id == staff_id,
        StaffLeave.leave_type == LeaveType.UNPAID,
        StaffLeave.deleted_at.is_(None),
        StaffLeave.start_date <= period_end,
        StaffLeave.end_date >= period_start,
    ).all()
    total = Decimal("0")
    for record in records:
        overlap_start = max(record.start_date, period_start)
        overlap_end = min(record.end_date, period_end)
        total += Decimal((overlap_end - overlap_start).days + 1) * Decimal(record.day_fraction)
    return total


@router.post("", response_model=StaffLeaveResponse)
def create_leave(
    payload: StaffLeaveCreate,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    user: User = Depends(require_role("gym_owner")),
):
    _staff_or_404(db, payload.staff_id, gym_id)
    leave = StaffLeave(gym_id=gym_id, **payload.model_dump())
    db.add(leave)
    from app.models.activity_log import ActivityLog
    db.add(ActivityLog(gym_id=gym_id, actor_id=user.id, action="leave_created", description=f"Recorded {payload.leave_type.value} leave for staff {payload.staff_id}"))
    db.commit()
    db.refresh(leave)
    return leave


@router.get("", response_model=List[StaffLeaveResponse])
def list_leave(
    staff_id: Optional[uuid.UUID] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_role("gym_owner")),
):
    query = db.query(StaffLeave).filter(StaffLeave.gym_id == gym_id, StaffLeave.deleted_at.is_(None))
    if staff_id:
        query = query.filter(StaffLeave.staff_id == staff_id)
    if start_date:
        query = query.filter(StaffLeave.end_date >= start_date)
    if end_date:
        query = query.filter(StaffLeave.start_date <= end_date)
    return query.order_by(StaffLeave.start_date.desc()).all()


@router.delete("/{leave_id}", status_code=204)
def delete_leave(
    leave_id: uuid.UUID,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    user: User = Depends(require_role("gym_owner")),
):
    leave = db.query(StaffLeave).filter(StaffLeave.id == leave_id, StaffLeave.gym_id == gym_id, StaffLeave.deleted_at.is_(None)).first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave record not found")
    leave.deleted_at = datetime.utcnow()
    from app.models.activity_log import ActivityLog
    db.add(ActivityLog(gym_id=gym_id, actor_id=user.id, action="leave_deleted", description=f"Deleted leave record {leave_id}"))
    db.commit()