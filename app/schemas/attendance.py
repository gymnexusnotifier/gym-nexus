import uuid
from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CheckInRequest(BaseModel):
    member_id: uuid.UUID


class AttendanceResponse(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    date: date
    check_in_time: str
    check_out_time: Optional[str] = None
    status: str

    model_config = ConfigDict(from_attributes=True)
