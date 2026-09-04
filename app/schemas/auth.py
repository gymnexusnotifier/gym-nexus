import uuid
from typing import Optional

from pydantic import BaseModel, EmailStr, ConfigDict


class SignupRequest(BaseModel):
    gym_name: str
    owner_email: EmailStr
    owner_password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: str
    gym_id: Optional[uuid.UUID] = None

    model_config = ConfigDict(from_attributes=True)
