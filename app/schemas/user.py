import uuid

from pydantic import BaseModel, EmailStr, ConfigDict


class StaffCreate(BaseModel):
    email: EmailStr
    password: str
    role: str  # "staff" or "trainer"


class StaffResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: str

    model_config = ConfigDict(from_attributes=True)
