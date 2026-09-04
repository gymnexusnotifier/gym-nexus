import uuid

from pydantic import BaseModel


class ChurnRiskResponse(BaseModel):
    member_id: uuid.UUID
    member_name: str
    risk_level: str
    reason: str
