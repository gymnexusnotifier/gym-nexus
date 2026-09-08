import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import LeaveType


class StaffLeaveCreate(BaseModel):
    staff_id: uuid.UUID
    start_date: date
    end_date: date
    leave_type: LeaveType = LeaveType.UNPAID
    day_fraction: Decimal = Field(default=Decimal("1"), gt=0, le=1)
    note: Optional[str] = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class StaffLeaveResponse(BaseModel):
    id: uuid.UUID
    staff_id: uuid.UUID
    start_date: date
    end_date: date
    leave_type: LeaveType
    day_fraction: Decimal
    note: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)