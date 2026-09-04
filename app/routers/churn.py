import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role, get_current_gym_id
from app.models.member import Member, MemberStatus
from app.schemas.churn import ChurnRiskResponse
from app.services.churn import compute_churn_risk

router = APIRouter(prefix="/churn", tags=["churn (AI insight)"])

_LEVEL_ORDER = {"low": 0, "medium": 1, "high": 2}


@router.get("/at-risk", response_model=List[ChurnRiskResponse])
def list_at_risk_members(
    min_level: str = "medium",
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_role("gym_owner", "staff")),
):
    threshold = _LEVEL_ORDER.get(min_level, 1)

    members = db.query(Member).filter(
        Member.gym_id == gym_id, Member.status == MemberStatus.ACTIVE
    ).all()

    results = []
    for member in members:
        risk = compute_churn_risk(db, gym_id, member)
        if _LEVEL_ORDER.get(risk["risk_level"], 0) >= threshold:
            results.append(ChurnRiskResponse(
                member_id=member.id,
                member_name=member.name,
                risk_level=risk["risk_level"],
                reason=risk["reason"],
            ))

    results.sort(key=lambda r: _LEVEL_ORDER[r.risk_level], reverse=True)
    return results


@router.get("/{member_id}", response_model=ChurnRiskResponse)
def get_member_churn_risk(
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_role("gym_owner", "staff")),
):
    member = db.query(Member).filter(Member.id == member_id, Member.gym_id == gym_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    risk = compute_churn_risk(db, gym_id, member)
    return ChurnRiskResponse(
        member_id=member.id,
        member_name=member.name,
        risk_level=risk["risk_level"],
        reason=risk["reason"],
    )
