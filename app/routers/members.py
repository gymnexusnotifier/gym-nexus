import uuid
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role, require_permission, get_current_gym_id
from app.core.email import send_email
from app.core.storage import save_member_photo, get_member_photo, member_photo_exists, member_photo_content_type
from app.models.member import Member, MembershipPlan, MemberStatus
from app.models.attendance import Attendance
from app.schemas.member import MemberCreate, MemberUpdate, MemberResponse, PlanCreate, PlanResponse

router = APIRouter(prefix="/members", tags=["members"])
plans_router = APIRouter(prefix="/plans", tags=["plans"])


def _send_member_welcome_email(db: Session, member: Member) -> bool:
    if not member.email:
        return False

    from app.models.gym import Gym

    gym_entry = db.query(Gym).filter(Gym.id == member.gym_id).first()
    gym_name = gym_entry.name if gym_entry else "Your gym"

    plan_name = "Signature Membership"
    if member.plan_id:
        from app.models.member import MembershipPlan
        plan = db.query(MembershipPlan).filter(MembershipPlan.id == member.plan_id).first()
        if plan:
            plan_name = plan.name

    subject = f"Welcome to {gym_name}"
    body = f"""
    <html>
      <body style="margin:0;padding:0;background:linear-gradient(135deg,#090b1a,#121f32 40%,#1f1637);font-family:Arial,Helvetica,sans-serif;color:#edf6ff;">
        <div style="max-width:620px;margin:32px auto;background:rgba(10,14,22,0.8);border:1px solid rgba(124,92,255,0.35);border-radius:18px;padding:28px;box-shadow:0 20px 60px rgba(12,18,36,0.7);">
          <div style="font-size:12px;letter-spacing:2px;text-transform:uppercase;color:#7dd3fc;margin-bottom:20px;">AI fitness onboarding</div>
          <h1 style="margin:0 0 18px;font-size:32px;line-height:1.2;color:#f5f7ff;">Welcome aboard, {member.name}.</h1>
          <p style="margin:0 0 18px;font-size:16px;line-height:1.7;color:#dfeaff;">
            Your membership at <strong>{gym_name}</strong> is now active. You are on the <strong>{plan_name}</strong> plan, and your smart check-in experience is ready to go.
          </p>
          <div style="background:linear-gradient(90deg,#3b82f6,#7c3aed,#22d3ee);border-radius:12px;padding:18px 20px;margin:20px 0;color:#fff;font-weight:700;letter-spacing:0.3px;">
            Face scan enabled • Smart attendance • AI-powered gym insights
          </div>
          <p style="margin:0 0 18px;font-size:15px;line-height:1.7;color:#dfeaff;">
            Please keep your face ready for lightning-fast check-ins and check-outs. Your gym experience is now powered for smooth tracking, analytics, and smarter member engagement.
          </p>
          <p style="margin:0 0 8px;font-size:15px;color:#dfeaff;">Warm regards,</p>
          <p style="margin:0;font-size:16px;color:#7dd3fc;font-weight:700;">{gym_name}</p>
        </div>
      </body>
    </html>
    """
    return send_email(member.email, subject, body, is_html=True)


# ---- Membership plans (owner only) ----

@plans_router.post("", response_model=PlanResponse)
def create_plan(
    payload: PlanCreate,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_role("gym_owner")),
):
    plan = MembershipPlan(gym_id=gym_id, **payload.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@plans_router.get("", response_model=List[PlanResponse])
def list_plans(
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_permission("members")),
):
    return db.query(MembershipPlan).filter(MembershipPlan.gym_id == gym_id).all()


# ---- Members ----

def _get_member_or_404(member_id: uuid.UUID, gym_id: uuid.UUID, db: Session) -> Member:
    member = db.query(Member).filter(Member.id == member_id, Member.gym_id == gym_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


@router.post("", response_model=MemberResponse)
def create_member(
    payload: MemberCreate,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_permission("members")),
):
    if payload.plan_id:
        plan = db.query(MembershipPlan).filter(
            MembershipPlan.id == payload.plan_id, MembershipPlan.gym_id == gym_id
        ).first()
        if not plan:
            raise HTTPException(status_code=400, detail="Invalid plan_id for this gym")

    member = Member(gym_id=gym_id, **payload.model_dump())
    db.add(member)
    db.commit()
    db.refresh(member)
    _send_member_welcome_email(db, member)
    return member


@router.get("", response_model=List[MemberResponse])
def list_members(
    status: Optional[str] = None,
    inactive_days: Optional[int] = None,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_permission("members")),
):
    query = db.query(Member).filter(Member.gym_id == gym_id)

    if status:
        try:
            query = query.filter(Member.status == MemberStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status value")

    if inactive_days is not None:
        cutoff = date.today() - timedelta(days=inactive_days)
        last_visit_subq = (
            db.query(Attendance.member_id, func.max(Attendance.date).label("last_visit"))
            .filter(Attendance.gym_id == gym_id)
            .group_by(Attendance.member_id)
            .subquery()
        )
        query = query.outerjoin(
            last_visit_subq, Member.id == last_visit_subq.c.member_id
        ).filter(
            (last_visit_subq.c.last_visit.is_(None)) | (last_visit_subq.c.last_visit < cutoff)
        )

    return query.all()


@router.get("/{member_id}", response_model=MemberResponse)
def get_member(
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_permission("members")),
):
    return _get_member_or_404(member_id, gym_id, db)


@router.put("/{member_id}", response_model=MemberResponse)
def update_member(
    member_id: uuid.UUID,
    payload: MemberUpdate,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_permission("members")),
):
    member = _get_member_or_404(member_id, gym_id, db)
    update_data = payload.model_dump(exclude_unset=True)

    if "status" in update_data:
        try:
            update_data["status"] = MemberStatus(update_data["status"])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status value")

    for field, value in update_data.items():
        setattr(member, field, value)

    db.commit()
    db.refresh(member)
    return member


@router.delete("/{member_id}", status_code=204)
def delete_member(
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_role("gym_owner")),
):
    member = _get_member_or_404(member_id, gym_id, db)
    db.delete(member)
    db.commit()


# ---- Member photo ----

@router.post("/{member_id}/photo", response_model=MemberResponse)
def upload_member_photo(
    member_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_role("gym_owner", "staff")),
):
    member = _get_member_or_404(member_id, gym_id, db)
    extension = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    contents = file.file.read()
    path = save_member_photo(str(gym_id), str(member_id), contents, extension)
    member.photo_path = path
    db.commit()
    db.refresh(member)
    return member


@router.get("/{member_id}/photo")
def get_member_photo(
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_role("gym_owner", "staff")),
):
    member = _get_member_or_404(member_id, gym_id, db)
    if not member_photo_exists(member.photo_path):
        raise HTTPException(status_code=404, detail="No photo uploaded for this member")
    return StreamingResponse(iter([get_member_photo(member.photo_path)]), media_type=member_photo_content_type(member.photo_path))
