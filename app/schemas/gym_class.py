import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class ClassCreate(BaseModel):
    name: str
    trainer_id: Optional[uuid.UUID] = None
    day_of_week: int  # 0=Monday .. 6=Sunday
    start_time: str   # "HH:MM"
    duration_minutes: int = 60
    capacity: int = 10

    @field_validator("day_of_week")
    @classmethod
    def validate_day(cls, v):
        if not 0 <= v <= 6:
            raise ValueError("day_of_week must be between 0 (Monday) and 6 (Sunday)")
        return v


class ClassUpdate(BaseModel):
    name: Optional[str] = None
    trainer_id: Optional[uuid.UUID] = None
    day_of_week: Optional[int] = None
    start_time: Optional[str] = None
    duration_minutes: Optional[int] = None
    capacity: Optional[int] = None


class ClassResponse(BaseModel):
    id: uuid.UUID
    name: str
    trainer_id: Optional[uuid.UUID] = None
    day_of_week: int
    start_time: str
    duration_minutes: int
    capacity: int
    booked_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class BookingCreate(BaseModel):
    member_id: uuid.UUID


class BookingResponse(BaseModel):
    id: uuid.UUID
    class_id: uuid.UUID
    member_id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)
