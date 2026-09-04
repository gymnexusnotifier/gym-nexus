import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role, require_permission, get_current_gym_id, get_current_user
from app.models.gym_class import GymClass, ClassBooking
from app.models.member import Member
from app.models.user import User
from app.models.enums import UserRole
from app.schemas.gym_class import ClassCreate, ClassUpdate, ClassResponse, BookingCreate, BookingResponse

router = APIRouter(prefix="/classes", tags=["classes"])


def _to_class_response(db: Session, gym_class: GymClass) -> ClassResponse:
    booked_count = db.query(ClassBooking).filter(ClassBooking.class_id == gym_class.id).count()
    return ClassResponse(
        id=gym_class.id,
        name=gym_class.name,
        trainer_id=gym_class.trainer_id,
        day_of_week=gym_class.day_of_week,
        start_time=gym_class.start_time,
        duration_minutes=gym_class.duration_minutes,
        capacity=gym_class.capacity,
        booked_count=booked_count,
    )


def _get_class_or_404(class_id: uuid.UUID, gym_id: uuid.UUID, db: Session) -> GymClass:
    gym_class = db.query(GymClass).filter(GymClass.id == class_id, GymClass.gym_id == gym_id).first()
    if not gym_class:
        raise HTTPException(status_code=404, detail="Class not found")
    return gym_class


@router.post("", response_model=ClassResponse)
def create_class(
    payload: ClassCreate,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_role("gym_owner")),
):
    if payload.trainer_id:
        trainer = db.query(User).filter(
            User.id == payload.trainer_id, User.gym_id == gym_id, User.role == UserRole.TRAINER
        ).first()
        if not trainer:
            raise HTTPException(status_code=400, detail="Invalid trainer_id for this gym")

    gym_class = GymClass(gym_id=gym_id, **payload.model_dump())
    db.add(gym_class)
    db.commit()
    db.refresh(gym_class)
    return _to_class_response(db, gym_class)


@router.get("", response_model=List[ClassResponse])
def list_classes(
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_permission("classes")),
):
    classes = db.query(GymClass).filter(GymClass.gym_id == gym_id).order_by(
        GymClass.day_of_week, GymClass.start_time
    ).all()
    return [_to_class_response(db, c) for c in classes]


@router.get("/mine", response_model=List[ClassResponse])
def list_my_classes(
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    current_user: User = Depends(get_current_user),
    _=Depends(require_role("trainer")),
):
    classes = db.query(GymClass).filter(
        GymClass.gym_id == gym_id, GymClass.trainer_id == current_user.id
    ).order_by(GymClass.day_of_week, GymClass.start_time).all()
    return [_to_class_response(db, c) for c in classes]


@router.get("/{class_id}", response_model=ClassResponse)
def get_class(
    class_id: uuid.UUID,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_permission("classes")),
):
    gym_class = _get_class_or_404(class_id, gym_id, db)
    return _to_class_response(db, gym_class)


@router.put("/{class_id}", response_model=ClassResponse)
def update_class(
    class_id: uuid.UUID,
    payload: ClassUpdate,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_role("gym_owner")),
):
    gym_class = _get_class_or_404(class_id, gym_id, db)
    update_data = payload.model_dump(exclude_unset=True)

    if update_data.get("trainer_id"):
        trainer = db.query(User).filter(
            User.id == update_data["trainer_id"], User.gym_id == gym_id, User.role == UserRole.TRAINER
        ).first()
        if not trainer:
            raise HTTPException(status_code=400, detail="Invalid trainer_id for this gym")

    for field, value in update_data.items():
        setattr(gym_class, field, value)

    db.commit()
    db.refresh(gym_class)
    return _to_class_response(db, gym_class)


@router.delete("/{class_id}", status_code=204)
def delete_class(
    class_id: uuid.UUID,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_role("gym_owner")),
):
    gym_class = _get_class_or_404(class_id, gym_id, db)
    db.delete(gym_class)
    db.commit()


@router.post("/{class_id}/book", response_model=BookingResponse)
def book_class(
    class_id: uuid.UUID,
    payload: BookingCreate,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_permission("classes")),
):
    gym_class = _get_class_or_404(class_id, gym_id, db)

    member = db.query(Member).filter(Member.id == payload.member_id, Member.gym_id == gym_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found for this gym")

    current_bookings = db.query(ClassBooking).filter(ClassBooking.class_id == class_id).count()
    if current_bookings >= gym_class.capacity:
        raise HTTPException(status_code=400, detail="Class is at full capacity")

    booking = ClassBooking(gym_id=gym_id, class_id=class_id, member_id=member.id)
    db.add(booking)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Member is already booked into this class")

    db.refresh(booking)
    return booking


@router.get("/{class_id}/bookings", response_model=List[BookingResponse])
def list_class_bookings(
    class_id: uuid.UUID,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_permission("classes")),
):
    _get_class_or_404(class_id, gym_id, db)
    return db.query(ClassBooking).filter(ClassBooking.class_id == class_id).all()
