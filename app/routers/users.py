import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role, get_current_gym_id
from app.core.security import hash_password
from app.models.user import User
from app.models.enums import UserRole
from app.schemas.user import StaffCreate, StaffResponse

router = APIRouter(prefix="/users", tags=["users"])

ALLOWED_INVITE_ROLES = {"staff", "trainer"}


@router.post("/staff", response_model=StaffResponse)
def create_staff(
    payload: StaffCreate,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_role("gym_owner")),
):
    if payload.role not in ALLOWED_INVITE_ROLES:
        raise HTTPException(status_code=400, detail="role must be 'staff' or 'trainer'")

    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        gym_id=gym_id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=UserRole(payload.role),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
