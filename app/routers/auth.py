from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.core.deps import get_current_user
from app.models.gym import Gym
from app.models.user import User
from app.models.enums import UserRole
from app.schemas.auth import SignupRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.owner_email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    gym = Gym(
        name=payload.gym_name,
        subscription_status="trial",
        trial_ends_at=date.today() + timedelta(days=14),
    )
    db.add(gym)
    db.flush()

    owner = User(
        gym_id=gym.id,
        email=payload.owner_email,
        hashed_password=hash_password(payload.owner_password),
        role=UserRole.GYM_OWNER,
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    token = create_access_token({
        "sub": str(owner.id),
        "gym_id": str(owner.gym_id),
        "role": owner.role.value,
    })
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    token = create_access_token({
        "sub": str(user.id),
        "gym_id": str(user.gym_id) if user.gym_id else None,
        "role": user.role.value,
    })
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user
