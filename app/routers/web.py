import base64
import csv
import os
import uuid
from datetime import date, datetime, timedelta
from io import BytesIO, StringIO

import numpy as np
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse, StreamingResponse, FileResponse, Response
from fastapi.templating import Jinja2Templates
from PIL import Image
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import verify_password, decode_access_token, create_access_token, hash_password
from app.core.email import send_email, build_payment_confirmation_email, build_staff_invitation_email, build_gym_owner_welcome_email
from app.core.deps import has_permission
from app.core.razorpay_client import get_razorpay_client
from app.models.user import User
from app.models.enums import UserRole
from app.models.member import Member, MemberStatus, MembershipPlan
from app.models.attendance import Attendance
from app.models.payment import Payment
from app.models.gym import Gym
from app.models.gym_class import GymClass, ClassBooking
from app.models.platform_plan import PlatformPlan
from app.models.activity_log import ActivityLog
from app.models.user_permission import UserPermission
from app.services.ai_insights import build_ai_snapshot
from app.services.chatbot import ask_chatbot, suggested_questions
from app.services.churn import compute_churn_risk
from app.services.face_engine import FaceRecognitionService
from app.services.receipt import generate_receipt_pdf
from app.core.storage import save_member_photo, get_member_photo, member_photo_exists, member_photo_content_type
from app.core.storage import get_support_attachment
from app.models.support import SupportAttachment, SupportAuditEvent, SupportMessage, SupportTicket, TicketPriority, TicketStatus
from app.services.support import add_attachments, add_message, change_status, create_ticket, get_ticket_for_user, notify_ticket_parties
from app.schemas.chatbot import ChatbotQuestionRequest

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
NOT_LINKED_MSG = "This+account+is+not+linked+to+a+gym.+Log+in+with+a+gym+owner+or+staff+account."
FACE_MATCH_TOLERANCE = 0.5
CHECKOUT_MIN_GAP_MINUTES = 15
MANAGED_PERMISSIONS = [
    ("dashboard", "Dashboard"),
    ("members", "Members"),
    ("attendance", "Attendance"),
    ("payments", "Payments"),
    ("classes", "Classes"),
    ("inquiries", "Inquiries"),
    ("notifications", "Notifications"),
]


def _log_activity(db: Session, user: User, action: str, description: str):
    if user.gym_id and user.role in (UserRole.STAFF, UserRole.TRAINER):
        db.add(ActivityLog(gym_id=user.gym_id, actor_id=user.id, action=action, description=description))


def _check_web_permission(db: Session, user: User, permission: str, redirect_path: str):
    if not has_permission(db, user, permission):
        return RedirectResponse(f"{redirect_path}?error=This+privilege+is+not+enabled+for+your+account", status_code=303)
    return None


def _minutes_since_checkin(check_in_time: str) -> float | None:
    try:
        check_in_dt = datetime.strptime(f"{date.today()} {check_in_time}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return (datetime.now() - check_in_dt).total_seconds() / 60


def _auto_close_stale_attendance(db: Session, gym_id: uuid.UUID):
    open_records = db.query(Attendance).filter(
        Attendance.gym_id == gym_id,
        Attendance.check_out_time.is_(None),
    ).all()

    for record in open_records:
        if record.check_in_time is None:
            continue
        if record.date < date.today():
            record.check_out_time = "23:59:59"
            continue

        minutes_since = _minutes_since_checkin(record.check_in_time)
        if minutes_since is not None and minutes_since >= CHECKOUT_MIN_GAP_MINUTES:
            record.check_out_time = datetime.now().strftime("%H:%M:%S")

    if open_records:
        db.commit()


def _toggle_attendance_for_member(db: Session, gym_id: uuid.UUID, member_id: uuid.UUID):
    member = db.query(Member).filter(Member.id == member_id, Member.gym_id == gym_id).first()
    if not member:
        raise ValueError("Member not found")

    _auto_close_stale_attendance(db, gym_id)

    today = date.today()
    now_str = datetime.now().strftime("%H:%M:%S")
    existing = db.query(Attendance).filter(
        Attendance.gym_id == gym_id,
        Attendance.member_id == member.id,
        Attendance.date == today,
    ).first()

    if existing is None:
        record = Attendance(
            gym_id=gym_id,
            member_id=member.id,
            date=today,
            check_in_time=now_str,
            status="present",
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record, "checked_in"

    if existing.check_out_time is None:
        minutes_since = _minutes_since_checkin(existing.check_in_time)
        if minutes_since is not None and minutes_since < CHECKOUT_MIN_GAP_MINUTES:
            return existing, "too_soon"
        existing.check_out_time = now_str
        db.commit()
        db.refresh(existing)
        return existing, "checked_out"

    return existing, "already_marked"


def _known_face_index(db: Session, gym_id: uuid.UUID):
    return FaceRecognitionService.build_known_faces(db, gym_id)


def get_web_user(request: Request, db: Session):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        return db.query(User).filter(User.id == uuid.UUID(user_id)).first()
    except Exception:
        return None


def _require_gym_user(request: Request, db: Session):
    user = get_web_user(request, db)
    if not user:
        return None, RedirectResponse("/login", status_code=303)
    if not user.gym_id:
        return None, RedirectResponse(f"/login?error={NOT_LINKED_MSG}", status_code=303)
    request.state.permissions = {permission: has_permission(db, user, permission) for permission, _ in MANAGED_PERMISSIONS}
    return user, None


def _build_inquiry_reminder_email(inquiry, recipient_name: str | None = None, gym_name: str | None = None) -> tuple[str, str]:
    plan_name = inquiry.plan.name if inquiry.plan else "Not selected"
    next_followup = inquiry.next_followup.isoformat() if inquiry.next_followup else "As scheduled"
    gym_name = (gym_name or getattr(inquiry, 'gym_name', '') or 'Your gym').strip() or 'Your gym'
    recipient_label = (recipient_name or inquiry.name or "there").strip() or "there"
    subject = f"{gym_name} follow-up: Let’s get you moving"
    body = f"""
    <html>
      <body style="margin:0;padding:0;background:linear-gradient(135deg,#07111f,#111827 35%,#1c1236);font-family:Arial,Helvetica,sans-serif;color:#edf6ff;">
        <div style="max-width:700px;margin:30px auto;padding:30px;border-radius:20px;background:rgba(8,15,27,0.88);border:1px solid rgba(103,232,249,0.18);box-shadow:0 26px 60px rgba(2,6,23,0.75);">
          <div style="font-size:12px;letter-spacing:2px;text-transform:uppercase;color:#7dd3fc;font-weight:700;margin-bottom:14px;">Your next step starts here</div>
          <h2 style="margin:0 0 12px;font-size:30px;color:#ffffff;line-height:1.2;">Hi {recipient_label},</h2>
          <p style="margin:0 0 18px;font-size:16px;line-height:1.8;color:#dbeafe;">
            We loved speaking with you about joining <strong>{gym_name}</strong> and we’d be happy to help you take the next step toward your fitness goals.
            We noticed your follow-up is scheduled for <strong>{next_followup}</strong>, and we’d love to keep the conversation going.
          </p>

          <div style="background:linear-gradient(135deg,rgba(34,197,94,0.12),rgba(103,232,249,0.08));border:1px solid rgba(103,232,249,0.2);border-radius:14px;padding:18px 20px;margin:18px 0;">
            <div style="font-size:14px;color:#dff7ef;"><strong>Plan:</strong> {plan_name}</div>
            <div style="font-size:14px;color:#dff7ef;"><strong>Preferred follow-up:</strong> {next_followup}</div>
            <div style="font-size:14px;color:#dff7ef;"><strong>Next move:</strong> We can answer your questions, help you choose the best plan, and get you started with a quick onboarding call.</div>
          </div>

          <p style="margin:0 0 20px;font-size:15px;line-height:1.8;color:#dbeafe;">
            Whether your goal is fat loss, strength, overall fitness, or just getting back into a routine, we are here to help you make it simple and consistent.
            If you’re ready, reply to this email or speak with our team and we’ll guide you from there.
          </p>

          <div style="margin:24px 0;">
            <a href="mailto:{inquiry.email or 'hello@example.com'}?subject=I%20want%20to%20join%20{gym_name}" style="display:inline-block;padding:12px 18px;border-radius:10px;background:linear-gradient(135deg,#67e8f9,#7c3aed);color:#07111f;text-decoration:none;font-weight:800;letter-spacing:0.04em;">Reply to start</a>
          </div>

          <p style="margin:0;color:#9fbfda;font-size:13px;line-height:1.8;">
            Looking forward to helping you begin your fitness journey.<br>
            <strong style="color:#67e8f9;">{gym_name}</strong>
          </p>
        </div>
      </body>
    </html>
    """
    return subject, body


# ---- Auth ----

@router.get("/", response_class=HTMLResponse)
def root(request: Request, db: Session = Depends(get_db)):
    user = get_web_user(request, db)
    if user:
        if user.role == UserRole.SUPER_ADMIN:
            return RedirectResponse("/app/superadmin", status_code=303)
        return RedirectResponse("/app/dashboard", status_code=303)
    return RedirectResponse("/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str = None):
    return templates.TemplateResponse(request, "login.html", {"error": error})


@router.post("/login")
def login_submit(email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return RedirectResponse("/login?error=Invalid+email+or+password", status_code=303)

    token = create_access_token({
        "sub": str(user.id),
        "gym_id": str(user.gym_id) if user.gym_id else None,
        "role": user.role.value,
    })
    landing = "/app/superadmin" if user.role == UserRole.SUPER_ADMIN else "/app/dashboard"
    response = RedirectResponse(landing, status_code=303)
    response.set_cookie("access_token", token, httponly=True, max_age=60 * 60 * 24, samesite="lax")
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("access_token")
    return response


# ---- Dashboard ----

@router.get("/app/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    blocked = _check_web_permission(db, user, "dashboard", "/login")
    if blocked:
        return blocked

    gym_id = user.gym_id
    gym = db.query(Gym).filter(Gym.id == gym_id).first()
    today = date.today()

    today_checkins = db.query(Attendance).filter(Attendance.gym_id == gym_id, Attendance.date == today).count()
    currently_in_gym = db.query(Attendance).filter(
        Attendance.gym_id == gym_id, Attendance.date == today, Attendance.check_out_time.is_(None)
    ).count()
    active_members = db.query(Member).filter(Member.gym_id == gym_id, Member.status == MemberStatus.ACTIVE).count()
    expired_members = db.query(Member).filter(Member.gym_id == gym_id, Member.status == MemberStatus.EXPIRED).count()

    month_start = today.replace(day=1)
    monthly_revenue = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.gym_id == gym_id, Payment.payment_date >= month_start
    ).scalar()
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    previous_month_revenue = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.gym_id == gym_id,
        Payment.payment_date >= last_month_start,
        Payment.payment_date < month_start,
    ).scalar()

    cutoff = today - timedelta(days=30)
    records = db.query(Attendance.check_in_time).filter(Attendance.gym_id == gym_id, Attendance.date >= cutoff).all()
    hour_counts = {}
    for (time_str,) in records:
        hour = int(time_str.split(":")[0])
        hour_counts[hour] = hour_counts.get(hour, 0) + 1
    max_count = max(hour_counts.values()) if hour_counts else 1
    peak_hours = [
        {"hour": h, "count": hour_counts.get(h, 0), "pct": round(hour_counts.get(h, 0) / max_count * 100)}
        for h in range(24) if hour_counts.get(h, 0) > 0
    ]
    busiest_hour = max(hour_counts, key=hour_counts.get) if hour_counts else None
    quietest_hour = min(hour_counts, key=hour_counts.get) if hour_counts else None
    visit_durations = []
    for attendance in db.query(Attendance).filter(
        Attendance.gym_id == gym_id,
        Attendance.date >= cutoff,
        Attendance.check_out_time.isnot(None),
    ).all():
        try:
            checked_in = datetime.strptime(attendance.check_in_time, "%H:%M:%S")
            checked_out = datetime.strptime(attendance.check_out_time, "%H:%M:%S")
            duration = (checked_out - checked_in).total_seconds() / 60
            if duration >= 0:
                visit_durations.append(duration)
        except (TypeError, ValueError):
            continue

    active = db.query(Member).filter(Member.gym_id == gym_id, Member.status == MemberStatus.ACTIVE).all()
    at_risk = []
    for m in active:
        risk = compute_churn_risk(db, gym_id, m)
        if risk["risk_level"] in ("medium", "high"):
            at_risk.append({"name": m.name, "level": risk["risk_level"], "reason": risk["reason"]})

    at_risk.sort(key=lambda r: {"high": 2, "medium": 1}.get(r["level"], 0), reverse=True)

    ai_snapshot = build_ai_snapshot(db, gym_id)
    plan_summary = (
        db.query(MembershipPlan.name, func.count(Member.id).label("member_count"))
        .outerjoin(Member, Member.plan_id == MembershipPlan.id)
        .filter(MembershipPlan.gym_id == gym_id)
        .group_by(MembershipPlan.name)
        .order_by(func.count(Member.id).desc())
        .all()
    )

    # Follow-ups due for this gym (owner-facing): inquiries with next_followup == today
    from app.models.inquiry import Inquiry
    due_inquiries = db.query(Inquiry).filter(Inquiry.gym_id == gym_id, Inquiry.next_followup == today).order_by(Inquiry.next_followup.asc()).all()
    followups_due_today = len(due_inquiries)
    due_list = []
    for iq in due_inquiries[:10]:
        assigned = None
        if iq.assigned_staff_id:
            u = db.query(User).filter(User.id == iq.assigned_staff_id).first()
            assigned = u.email if u else None
        due_list.append({"id": str(iq.id), "name": iq.name, "next_followup": iq.next_followup, "assigned": assigned})

    attendance_30_days = len(records)
    average_daily_checkins = round(attendance_30_days / 30, 1)
    total_members = db.query(Member).filter(Member.gym_id == gym_id).count()
    conversion_candidates = db.query(Inquiry).filter(Inquiry.gym_id == gym_id).count()
    converted_inquiries = db.query(Inquiry).filter(
        Inquiry.gym_id == gym_id, Inquiry.status == "converted"
    ).count()
    conversion_rate = round(converted_inquiries / conversion_candidates * 100, 1) if conversion_candidates else 0
    renewal_pipeline = db.query(Payment).filter(
        Payment.gym_id == gym_id,
        Payment.next_due_date.isnot(None),
        Payment.next_due_date >= today,
        Payment.next_due_date <= today + timedelta(days=30),
    ).count()
    revenue_per_active_member = round(float(monthly_revenue or 0) / active_members, 2) if active_members else 0
    revenue_change = None
    if previous_month_revenue:
        revenue_change = round((float(monthly_revenue or 0) - float(previous_month_revenue)) / float(previous_month_revenue) * 100, 1)
    if active_members:
        capacity_signal = round(attendance_30_days / active_members, 1)
    else:
        capacity_signal = 0

    ai_metrics = {
        "attendance_30_days": attendance_30_days,
        "average_daily_checkins": average_daily_checkins,
        "total_members": total_members,
        "frozen_members": db.query(Member).filter(Member.gym_id == gym_id, Member.status == MemberStatus.FROZEN).count(),
        "conversion_rate": conversion_rate,
        "conversion_candidates": conversion_candidates,
        "renewal_pipeline": renewal_pipeline,
        "revenue_per_active_member": revenue_per_active_member,
        "revenue_change": revenue_change,
        "attendance_per_active_member": capacity_signal,
    }

    return templates.TemplateResponse(request, "dashboard.html", {
        "active_nav": "dashboard",
        "gym_name": gym.name,
        "user_role": user.role.value,
        "today_checkins": today_checkins,
        "currently_in_gym": currently_in_gym,
        "active_members": active_members,
        "expired_members": expired_members,
        "monthly_revenue": monthly_revenue,
        "peak_hours": peak_hours,
        "at_risk": at_risk,
        "ai_snapshot": ai_snapshot,
        "plan_summary": [
            {"name": name, "member_count": count}
            for name, count in plan_summary
        ],
        "face_recognition_available": FaceRecognitionService.available(),
        "followups_due_today": followups_due_today,
        "due_inquiries": due_list,
        "ai_metrics": ai_metrics,
        "busiest_hour": busiest_hour,
        "quietest_hour": quietest_hour,
        "average_visit_minutes": round(sum(visit_durations) / len(visit_durations)) if visit_durations else None,
        "chatbot_questions": suggested_questions(),
    })


@router.post("/app/chatbot/ask")
def chatbot_ask(payload: ChatbotQuestionRequest, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    blocked = _check_web_permission(db, user, "dashboard", "/login")
    if blocked:
        return blocked

    gym_id = user.gym_id
    today = date.today()
    month_start = today.replace(day=1)
    facts = {
        "active_members": db.query(Member).filter(
            Member.gym_id == gym_id, Member.status == MemberStatus.ACTIVE
        ).count(),
        "new_members": db.query(Member).filter(
            Member.gym_id == gym_id, Member.join_date >= month_start
        ).count(),
        "expiring_memberships": db.query(Payment).filter(
            Payment.gym_id == gym_id,
            Payment.next_due_date >= today,
            Payment.next_due_date <= today + timedelta(days=30),
        ).count(),
        "expired_members": db.query(Member).filter(
            Member.gym_id == gym_id, Member.status == MemberStatus.EXPIRED
        ).count(),
        "monthly_revenue": db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
            Payment.gym_id == gym_id, Payment.payment_date >= month_start
        ).scalar(),
        "today_checkins": db.query(Attendance).filter(
            Attendance.gym_id == gym_id, Attendance.date == today
        ).count(),
        "inactive_members": db.query(Member).filter(
            Member.gym_id == gym_id, Member.status == MemberStatus.FROZEN
        ).count(),
    }
    plan_summary = (
        db.query(MembershipPlan.name, func.count(Member.id).label("member_count"))
        .outerjoin(Member, Member.plan_id == MembershipPlan.id)
        .filter(MembershipPlan.gym_id == gym_id)
        .group_by(MembershipPlan.name)
        .order_by(func.count(Member.id).desc())
        .limit(3)
        .all()
    )
    facts["popular_plans"] = ", ".join(
        f"{name} ({count})" for name, count in plan_summary if count
    )
    return ask_chatbot(payload.question, facts)


@router.get("/app/dashboard/report")
def download_dashboard_report(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect

    from app.models.inquiry import Inquiry
    today = date.today()
    month_start = today.replace(day=1)
    gym = db.query(Gym).filter(Gym.id == user.gym_id).first()
    members = db.query(Member).filter(Member.gym_id == user.gym_id).order_by(Member.name).all()
    attendance = db.query(Attendance).filter(
        Attendance.gym_id == user.gym_id,
        Attendance.date >= today - timedelta(days=30),
    ).count()
    revenue = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.gym_id == user.gym_id, Payment.payment_date >= month_start
    ).scalar()
    inquiries = db.query(Inquiry).filter(Inquiry.gym_id == user.gym_id).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["AI Insights Report", gym.name if gym else "Gym"])
    writer.writerow(["Generated", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")])
    writer.writerow([])
    writer.writerow(["Metric", "Value"])
    writer.writerow(["Members", len(members)])
    writer.writerow(["Active members", sum(m.status == MemberStatus.ACTIVE for m in members)])
    writer.writerow(["Expired members", sum(m.status == MemberStatus.EXPIRED for m in members)])
    writer.writerow(["Frozen members", sum(m.status == MemberStatus.FROZEN for m in members)])
    writer.writerow(["Attendance records (last 30 days)", attendance])
    writer.writerow(["Revenue (current month)", float(revenue or 0)])
    writer.writerow(["Leads", len(inquiries)])
    writer.writerow(["Converted leads", sum(i.status.value == "converted" for i in inquiries)])
    writer.writerow([])
    writer.writerow(["Member", "Status", "Join date", "Plan"])
    for member in members:
        writer.writerow([member.name, member.status.value, member.join_date.isoformat(), member.plan.name if member.plan else "Unassigned"])

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=ai_insights_{today.isoformat()}.csv"},
    )

# ---- Members ----

@router.get("/app/members", response_class=HTMLResponse)
def members_page(request: Request, error: str = None, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    blocked = _check_web_permission(db, user, "members", "/app/dashboard")
    if blocked:
        return blocked

    members = db.query(Member).filter(Member.gym_id == user.gym_id).order_by(Member.created_at.desc()).all()
    gym = db.query(Gym).filter(Gym.id == user.gym_id).first()
    plans = db.query(MembershipPlan).filter(MembershipPlan.gym_id == user.gym_id).order_by(MembershipPlan.price).all()

    member_rows = []
    for member in members:
        member_rows.append({
            "member": member,
            "plan_name": member.plan.name if member.plan else "No plan",
        })

    return templates.TemplateResponse(request, "members.html", {
        "active_nav": "members",
        "gym_name": gym.name,
        "user_role": user.role.value,
        "members": member_rows,
        "plans": plans,
        "error": error,
    })


@router.post("/app/members")
def create_member_web(
    request: Request,
    name: str = Form(...),
    contact: str = Form(""),
    email: str = Form(""),
    plan_id: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    blocked = _check_web_permission(db, user, "members", "/app/dashboard")
    if blocked:
        return blocked

    member_plan_id = None
    if plan_id:
        try:
            member_plan_id = uuid.UUID(plan_id)
            plan = db.query(MembershipPlan).filter(MembershipPlan.id == member_plan_id, MembershipPlan.gym_id == user.gym_id).first()
            if not plan:
                return RedirectResponse("/app/members?error=Selected+plan+not+found", status_code=303)
        except ValueError:
            return RedirectResponse("/app/members?error=Invalid+plan+selected", status_code=303)

    member = Member(
        gym_id=user.gym_id,
        name=name,
        contact=contact or None,
        email=email or None,
        plan_id=member_plan_id,
    )
    db.add(member)
    _log_activity(db, user, "member_created", f"Added member {name.strip()}")
    db.commit()
    db.refresh(member)

    if member.email:
        gym = db.query(Gym).filter(Gym.id == user.gym_id).first()
        plan_name = "Signature membership"
        if member.plan_id:
            selected_plan = db.query(MembershipPlan).filter(MembershipPlan.id == member.plan_id).first()
            if selected_plan:
                plan_name = selected_plan.name

        subject = f"Welcome to {gym.name if gym else 'Your gym'}"
        body = f"""
        <html>
          <body style="margin:0;padding:0;background:linear-gradient(135deg,#070b16,#111b2d 38%,#231730);font-family:Arial,Helvetica,sans-serif;color:#eef7ff;">
            <div style="max-width:620px;margin:32px auto;background:rgba(15,23,42,0.83);border:1px solid rgba(59,130,246,0.35);border-radius:18px;padding:28px;box-shadow:0 18px 46px rgba(2,6,23,0.72);">
              <div style="font-size:12px;letter-spacing:2px;text-transform:uppercase;color:#7dd3fc;margin-bottom:16px;">AI-powered onboarding</div>
              <h1 style="margin:0 0 18px;font-size:30px;line-height:1.2;color:#f8fbff;">Welcome, {member.name}. Your journey is live.</h1>
              <p style="margin:0 0 16px;font-size:16px;line-height:1.7;color:#dfeafc;">
                You have been successfully added to <strong>{gym.name if gym else 'your gym'}</strong> on the <strong>{plan_name}</strong> plan.
              </p>
              <div style="background:linear-gradient(90deg,#2563eb,#8b5cf6,#22d3ee);border-radius:12px;padding:18px 20px;margin:18px 0;color:#fff;font-weight:700;letter-spacing:0.2px;">
                Smart check-ins • AI insights • Performance tracking
              </div>
              <p style="margin:0 0 16px;font-size:15px;line-height:1.7;color:#dfeafc;">
                Keep your face ready for fast attendance scanning and access your stats through the gym dashboard.
              </p>
              <p style="margin:0 0 8px;font-size:15px;color:#dfeafc;">Best,</p>
              <p style="margin:0;font-size:16px;color:#7dd3fc;font-weight:700;">{gym.name if gym else 'Gym Management Team'}</p>
            </div>
          </body>
        </html>
        """
        send_email(member.email, subject, body, is_html=True)

    return RedirectResponse("/app/members?success=Member+created+successfully", status_code=303)


@router.get("/app/members/{member_id}", response_class=HTMLResponse)
def member_detail_page(member_id: str, request: Request, error: str = None, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect

    member = db.query(Member).filter(Member.id == uuid.UUID(member_id), Member.gym_id == user.gym_id).first()
    if not member:
        return RedirectResponse("/app/members?error=Member+not+found", status_code=303)

    gym = db.query(Gym).filter(Gym.id == user.gym_id).first()
    plans = db.query(MembershipPlan).filter(MembershipPlan.gym_id == user.gym_id).order_by(MembershipPlan.price).all()

    attendance_rows = db.query(Attendance).filter(
        Attendance.gym_id == user.gym_id, Attendance.member_id == member.id
    ).order_by(Attendance.date.desc()).all()
    attendance = [
        {"date": a.date, "check_in": a.check_in_time, "check_out": a.check_out_time}
        for a in attendance_rows
    ]

    rows = (
        db.query(Payment, MembershipPlan)
        .outerjoin(MembershipPlan, MembershipPlan.id == Payment.plan_id)
        .filter(Payment.gym_id == user.gym_id, Payment.member_id == member.id)
        .order_by(Payment.payment_date.desc())
        .all()
    )
    payment_rows = [
        {"id": p.id, "date": p.payment_date, "plan": pl.name if pl else "—", "amount": p.amount}
        for p, pl in rows
    ]

    risk = compute_churn_risk(db, user.gym_id, member)

    has_photo = member_photo_exists(member.photo_path)

    return templates.TemplateResponse(request, "member_detail.html", {
        "active_nav": "members",
        "gym_name": gym.name,
        "user_role": user.role.value,
        "member": member,
        "plans": plans,
        "attendance": attendance,
        "payments": payment_rows,
        "churn": risk,
        "error": error,
        "has_photo": has_photo,
    })


@router.post("/app/members/{member_id}")
def update_member_web(
    member_id: str,
    request: Request,
    name: str = Form(...),
    contact: str = Form(""),
    email: str = Form(""),
    status: str = Form(...),
    plan_id: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    blocked = _check_web_permission(db, user, "members", "/app/dashboard")
    if blocked:
        return blocked

    member = db.query(Member).filter(Member.id == uuid.UUID(member_id), Member.gym_id == user.gym_id).first()
    if not member:
        return RedirectResponse("/app/members?error=Member+not+found", status_code=303)

    member.name = name
    member.contact = contact or None
    member.email = email or None
    if status:
        try:
            member.status = MemberStatus(status)
        except ValueError:
            pass

    if plan_id:
        try:
            selected_plan_id = uuid.UUID(plan_id)
            plan = db.query(MembershipPlan).filter(MembershipPlan.id == selected_plan_id, MembershipPlan.gym_id == user.gym_id).first()
            if not plan:
                return RedirectResponse(f"/app/members/{member_id}?error=Selected+plan+not+found", status_code=303)
            member.plan_id = selected_plan_id
        except ValueError:
            return RedirectResponse(f"/app/members/{member_id}?error=Invalid+plan+selected", status_code=303)

    db.commit()

    return RedirectResponse(f"/app/members/{member_id}", status_code=303)


@router.post("/app/members/{member_id}/delete")
def delete_member_web(member_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    if user.role != UserRole.GYM_OWNER:
        return RedirectResponse(f"/app/members/{member_id}?error=Only+the+owner+can+delete+members", status_code=303)

    member = db.query(Member).filter(Member.id == uuid.UUID(member_id), Member.gym_id == user.gym_id).first()
    if member:
        db.delete(member)
        db.commit()

    return RedirectResponse("/app/members", status_code=303)


# ---- Plans ----

@router.get("/app/plans", response_class=HTMLResponse)
def plans_page(request: Request, error: str = None, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect

    gym = db.query(Gym).filter(Gym.id == user.gym_id).first()
    plans = db.query(MembershipPlan).filter(MembershipPlan.gym_id == user.gym_id).order_by(MembershipPlan.price).all()

    return templates.TemplateResponse(request, "plans.html", {
        "active_nav": "plans",
        "gym_name": gym.name,
        "user_role": user.role.value,
        "plans": plans,
        "error": error,
    })


@router.post("/app/plans")
def create_plan_web(
    request: Request,
    name: str = Form(...),
    price: str = Form(...),
    duration_days: int = Form(...),
    db: Session = Depends(get_db),
):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    if user.role != UserRole.GYM_OWNER:
        return RedirectResponse("/app/plans?error=Only+the+owner+can+add+plans", status_code=303)

    plan = MembershipPlan(gym_id=user.gym_id, name=name, price=price, duration_days=duration_days)
    db.add(plan)
    db.commit()
    return RedirectResponse("/app/plans", status_code=303)


# ---- Payments ----

@router.get("/app/payments", response_class=HTMLResponse)
def payments_page(request: Request, error: str = None, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    blocked = _check_web_permission(db, user, "payments", "/app/dashboard")
    if blocked:
        return blocked

    gym = db.query(Gym).filter(Gym.id == user.gym_id).first()
    members = db.query(Member).filter(Member.gym_id == user.gym_id).order_by(Member.name).all()
    plans = db.query(MembershipPlan).filter(MembershipPlan.gym_id == user.gym_id).order_by(MembershipPlan.price).all()

    rows = (
        db.query(Payment, Member, MembershipPlan)
        .join(Member, Member.id == Payment.member_id)
        .outerjoin(MembershipPlan, MembershipPlan.id == Payment.plan_id)
        .filter(Payment.gym_id == user.gym_id)
        .order_by(Payment.payment_date.desc())
        .all()
    )
    payment_rows = [
        {"id": p.id, "date": p.payment_date, "member": m.name, "plan": pl.name if pl else "—", "amount": p.amount, "payment_method": p.payment_method, "transaction_id": p.transaction_id}
        for p, m, pl in rows
    ]

    return templates.TemplateResponse(request, "payments.html", {
        "active_nav": "payments",
        "gym_name": gym.name,
        "user_role": user.role.value,
        "members": members,
        "plans": plans,
        "payments": payment_rows,
        "error": error,
    })


@router.post("/app/payments")
def create_payment_web(
    request: Request,
    member_id: str = Form(...),
    plan_id: str = Form(""),
    amount: str = Form(...),
    payment_method: str = Form("cash"),
    transaction_id: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    blocked = _check_web_permission(db, user, "payments", "/app/dashboard")
    if blocked:
        return blocked
    if payment_method not in {"cash", "upi", "card", "bank_transfer"}:
        return RedirectResponse("/app/payments?error=Invalid+payment+method", status_code=303)
    if payment_method == "upi" and not transaction_id.strip():
        return RedirectResponse("/app/payments?error=UTR+or+transaction+ID+is+required+for+UPI+payments", status_code=303)

    member = db.query(Member).filter(Member.id == uuid.UUID(member_id), Member.gym_id == user.gym_id).first()
    if not member:
        return RedirectResponse("/app/payments?error=Member+not+found", status_code=303)
    gym = db.query(Gym).filter(Gym.id == user.gym_id).first()

    plan = None
    if plan_id:
        plan = db.query(MembershipPlan).filter(
            MembershipPlan.id == uuid.UUID(plan_id), MembershipPlan.gym_id == user.gym_id
        ).first()

    today = date.today()
    next_due = today + timedelta(days=plan.duration_days) if plan else None

    payment = Payment(
        gym_id=user.gym_id,
        member_id=member.id,
        plan_id=plan.id if plan else None,
        amount=amount,
        payment_date=today,
        next_due_date=next_due,
        payment_method=payment_method,
        transaction_id=transaction_id.strip() or None,
    )
    db.add(payment)
    _log_activity(db, user, "payment_recorded", f"Recorded payment for {member.name}: Rs. {amount}")
    member.status = MemberStatus.ACTIVE
    if plan:
        member.plan_id = plan.id
    db.commit()

    if member.email:
        subject, body = build_payment_confirmation_email(
            gym.name if gym else "Your gym",
            member.name,
            payment.amount,
            payment.payment_date,
            plan.name if plan else "General payment",
            payment.next_due_date,
            payment.payment_method,
            payment.transaction_id,
        )
        receipt = generate_receipt_pdf(gym.name if gym else "Gym", payment, member.name, plan.name if plan else "General payment")
        send_email(member.email, subject, body, is_html=True, attachments=[(f"receipt_{str(payment.id)[:8]}.pdf", receipt.read(), "application/pdf")])

    return RedirectResponse("/app/payments", status_code=303)


@router.get("/app/payments/{payment_id}/receipt")
def download_receipt_web(payment_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect

    payment = db.query(Payment).filter(
        Payment.id == uuid.UUID(payment_id), Payment.gym_id == user.gym_id
    ).first()
    if not payment:
        return RedirectResponse("/app/payments?error=Receipt+not+found", status_code=303)

    member = db.query(Member).filter(Member.id == payment.member_id).first()
    gym = db.query(Gym).filter(Gym.id == user.gym_id).first()
    plan = (
        db.query(MembershipPlan).filter(MembershipPlan.id == payment.plan_id).first()
        if payment.plan_id else None
    )

    buffer = generate_receipt_pdf(
        gym_name=gym.name if gym else "Gym",
        payment=payment,
        member_name=member.name if member else "Unknown",
        plan_name=plan.name if plan else "N/A",
    )

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=receipt_{str(payment.id)[:8]}.pdf"},
    )


# ---- Classes ----

@router.get("/app/classes", response_class=HTMLResponse)
def classes_page(request: Request, error: str = None, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    blocked = _check_web_permission(db, user, "classes", "/app/dashboard")
    if blocked:
        return blocked

    gym = db.query(Gym).filter(Gym.id == user.gym_id).first()
    classes = db.query(GymClass).filter(GymClass.gym_id == user.gym_id).order_by(
        GymClass.day_of_week, GymClass.start_time
    ).all()

    class_rows = []
    for c in classes:
        booked = db.query(ClassBooking).filter(ClassBooking.class_id == c.id).count()
        trainer = db.query(User).filter(User.id == c.trainer_id).first() if c.trainer_id else None
        class_rows.append({
            "id": c.id, "name": c.name, "day": DAY_NAMES[c.day_of_week], "time": c.start_time,
            "duration": c.duration_minutes, "trainer": trainer.email if trainer else "Unassigned",
            "booked": booked, "capacity": c.capacity,
        })

    trainers = db.query(User).filter(User.gym_id == user.gym_id, User.role == UserRole.TRAINER).all()
    members = db.query(Member).filter(Member.gym_id == user.gym_id).order_by(Member.name).all()

    return templates.TemplateResponse(request, "classes.html", {
        "active_nav": "classes",
        "gym_name": gym.name,
        "user_role": user.role.value,
        "classes": class_rows,
        "trainers": trainers,
        "members": members,
        "error": error,
    })


@router.post("/app/classes")
def create_class_web(
    request: Request,
    name: str = Form(...),
    trainer_id: str = Form(""),
    day_of_week: int = Form(...),
    start_time: str = Form(...),
    duration_minutes: int = Form(60),
    capacity: int = Form(10),
    db: Session = Depends(get_db),
):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    if user.role != UserRole.GYM_OWNER:
        return RedirectResponse("/app/classes?error=Only+the+owner+can+add+classes", status_code=303)

    gym_class = GymClass(
        gym_id=user.gym_id, name=name,
        trainer_id=uuid.UUID(trainer_id) if trainer_id else None,
        day_of_week=day_of_week, start_time=start_time,
        duration_minutes=duration_minutes, capacity=capacity,
    )
    db.add(gym_class)
    db.commit()
    return RedirectResponse("/app/classes", status_code=303)


@router.post("/app/classes/{class_id}/book")
def book_class_web(class_id: str, request: Request, member_id: str = Form(...), db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    blocked = _check_web_permission(db, user, "classes", "/app/dashboard")
    if blocked:
        return blocked

    gym_class = db.query(GymClass).filter(
        GymClass.id == uuid.UUID(class_id), GymClass.gym_id == user.gym_id
    ).first()
    if not gym_class:
        return RedirectResponse("/app/classes?error=Class+not+found", status_code=303)

    member = db.query(Member).filter(Member.id == uuid.UUID(member_id), Member.gym_id == user.gym_id).first()
    if not member:
        return RedirectResponse("/app/classes?error=Member+not+found", status_code=303)

    current_bookings = db.query(ClassBooking).filter(ClassBooking.class_id == gym_class.id).count()
    if current_bookings >= gym_class.capacity:
        return RedirectResponse("/app/classes?error=Class+is+at+full+capacity", status_code=303)

    existing = db.query(ClassBooking).filter(
        ClassBooking.class_id == gym_class.id, ClassBooking.member_id == member.id
    ).first()
    if existing:
        return RedirectResponse("/app/classes?error=Member+already+booked+into+this+class", status_code=303)

    booking = ClassBooking(gym_id=user.gym_id, class_id=gym_class.id, member_id=member.id)
    db.add(booking)
    _log_activity(db, user, "class_booked", f"Booked {member.name} into {gym_class.name}")
    db.commit()
    return RedirectResponse("/app/classes", status_code=303)


# ---- Trainer's own schedule ----

@router.get("/app/trainer/schedule", response_class=HTMLResponse)
def trainer_schedule_page(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect

    gym = db.query(Gym).filter(Gym.id == user.gym_id).first()
    classes = db.query(GymClass).filter(
        GymClass.gym_id == user.gym_id, GymClass.trainer_id == user.id
    ).order_by(GymClass.day_of_week, GymClass.start_time).all()

    class_rows = []
    for c in classes:
        booked = db.query(ClassBooking).filter(ClassBooking.class_id == c.id).count()
        class_rows.append({
            "name": c.name, "day": DAY_NAMES[c.day_of_week], "time": c.start_time,
            "duration": c.duration_minutes, "booked": booked, "capacity": c.capacity,
        })

    return templates.TemplateResponse(request, "trainer_schedule.html", {
        "active_nav": "trainer_schedule",
        "gym_name": gym.name,
        "user_role": user.role.value,
        "classes": class_rows,
    })


# ---- Support tickets ----

@router.get("/app/support", response_class=HTMLResponse)
def support_tickets_page(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    gym = db.query(Gym).filter(Gym.id == user.gym_id).first()
    tickets = db.query(SupportTicket).filter(SupportTicket.owner_id == user.id).order_by(SupportTicket.updated_at.desc()).all()
    return templates.TemplateResponse(request, "support_tickets.html", {
        "active_nav": "support", "gym_name": gym.name, "user_role": user.role.value, "tickets": tickets,
    })


@router.get("/app/support/new", response_class=HTMLResponse)
def new_support_ticket_page(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    gym = db.query(Gym).filter(Gym.id == user.gym_id).first()
    return templates.TemplateResponse(request, "support_new.html", {
        "active_nav": "support", "gym_name": gym.name, "user_role": user.role.value,
    })


@router.post("/app/support")
async def create_support_ticket_web(
    request: Request,
    subject: str = Form(...), description: str = Form(...), category: str = Form(...),
    priority: str = Form("normal"), attachments: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    if user.role != UserRole.GYM_OWNER:
        return RedirectResponse("/app/support?error=Only+the+gym+owner+can+raise+support+tickets", status_code=303)
    try:
        ticket = create_ticket(db, user, subject, description, category, priority)
        message = db.query(SupportMessage).filter(SupportMessage.ticket_id == ticket.id).first()
        add_attachments(db, ticket, message, user, attachments)
        db.commit()
        notify_ticket_parties(db, ticket, user, "New ticket created")
        return RedirectResponse(f"/app/support/{ticket.id}", status_code=303)
    except Exception as exc:
        db.rollback()
        return RedirectResponse(f"/app/support/new?error={str(exc).replace(' ', '+')[:180]}", status_code=303)


@router.get("/app/support/{ticket_id}", response_class=HTMLResponse)
def support_ticket_detail_page(ticket_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    try:
        ticket = get_ticket_for_user(db, uuid.UUID(ticket_id), user)
    except ValueError:
        ticket = None
    if not ticket:
        return RedirectResponse("/app/support?error=Ticket+not+found", status_code=303)
    gym = db.query(Gym).filter(Gym.id == ticket.gym_id).first()
    messages = db.query(SupportMessage).filter(
        SupportMessage.ticket_id == ticket.id, SupportMessage.is_internal == 0
    ).order_by(SupportMessage.created_at.asc()).all()
    attachments = db.query(SupportAttachment).filter(SupportAttachment.ticket_id == ticket.id).all()
    return templates.TemplateResponse(request, "support_detail.html", {
        "active_nav": "support", "gym_name": gym.name, "user_role": user.role.value,
        "ticket": ticket, "messages": messages, "attachments": attachments,
    })


@router.post("/app/support/{ticket_id}/reply")
async def reply_support_ticket_web(
    ticket_id: str, request: Request, content: str = Form(...), attachments: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    try:
        ticket = get_ticket_for_user(db, uuid.UUID(ticket_id), user)
    except ValueError:
        ticket = None
    if not ticket:
        return RedirectResponse("/app/support?error=Ticket+not+found", status_code=303)
    try:
        message = add_message(db, ticket, user, content)
        add_attachments(db, ticket, message, user, attachments)
        if user.role == UserRole.GYM_OWNER and ticket.status in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
            change_status(db, ticket, user, TicketStatus.REOPENED.value)
        db.commit()
        notify_ticket_parties(db, ticket, user, "New reply added")
    except Exception as exc:
        db.rollback()
        return RedirectResponse(f"/app/support/{ticket_id}?error={str(exc).replace(' ', '+')[:180]}", status_code=303)
    return RedirectResponse(f"/app/support/{ticket_id}", status_code=303)


@router.get("/app/support/attachments/{attachment_id}")
def support_attachment_download(attachment_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    try:
        attachment = db.query(SupportAttachment).filter(SupportAttachment.id == uuid.UUID(attachment_id)).first()
    except ValueError:
        attachment = None
    if not attachment:
        return Response(status_code=404)
    ticket = db.query(SupportTicket).filter(SupportTicket.id == attachment.ticket_id).first()
    if not ticket or (user.role != UserRole.SUPER_ADMIN and ticket.owner_id != user.id):
        return Response(status_code=403)
    try:
        content = get_support_attachment(attachment.storage_path)
    except (FileNotFoundError, OSError):
        return Response(status_code=404)
    return Response(content=content, media_type=attachment.content_type, headers={"Content-Disposition": f'inline; filename="{attachment.original_name}"'})


@router.get("/app/superadmin/support", response_class=HTMLResponse)
def superadmin_support_page(request: Request, q: str = "", status: str = "", db: Session = Depends(get_db)):
    user, redirect = _require_superadmin(request, db)
    if redirect:
        return redirect
    query = db.query(SupportTicket).order_by(SupportTicket.updated_at.desc())
    if q.strip():
        query = query.filter(SupportTicket.subject.ilike(f"%{q.strip()}%"))
    if status in {item.value for item in TicketStatus}:
        query = query.filter(SupportTicket.status == TicketStatus(status))
    tickets = query.all()
    ticket_rows = []
    for ticket in tickets:
        owner = db.query(User).filter(User.id == ticket.owner_id).first()
        gym = db.query(Gym).filter(Gym.id == ticket.gym_id).first()
        ticket_rows.append({"ticket": ticket, "owner_email": owner.email if owner else "Unknown", "gym_name": gym.name if gym else "Unknown"})
    return templates.TemplateResponse(request, "superadmin_support.html", {
        "active_section": "support", "user_role": user.role.value, "tickets": ticket_rows, "q": q, "selected_status": status,
    })


@router.get("/app/superadmin/support/{ticket_id}", response_class=HTMLResponse)
def superadmin_support_detail(ticket_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_superadmin(request, db)
    if redirect:
        return redirect
    try:
        ticket = db.query(SupportTicket).filter(SupportTicket.id == uuid.UUID(ticket_id)).first()
    except ValueError:
        ticket = None
    if not ticket:
        return RedirectResponse("/app/superadmin/support?error=Ticket+not+found", status_code=303)
    messages = db.query(SupportMessage).filter(SupportMessage.ticket_id == ticket.id).order_by(SupportMessage.created_at.asc()).all()
    attachments = db.query(SupportAttachment).filter(SupportAttachment.ticket_id == ticket.id).all()
    audits = db.query(SupportAuditEvent).filter(SupportAuditEvent.ticket_id == ticket.id).order_by(SupportAuditEvent.created_at.asc()).all()
    owner = db.query(User).filter(User.id == ticket.owner_id).first()
    gym = db.query(Gym).filter(Gym.id == ticket.gym_id).first()
    return templates.TemplateResponse(request, "superadmin_support_detail.html", {
        "active_section": "support", "user_role": user.role.value, "ticket": ticket, "messages": messages,
        "attachments": attachments, "audits": audits, "owner": owner, "gym": gym,
        "statuses": list(TicketStatus), "priorities": list(TicketPriority),
    })


@router.post("/app/superadmin/support/{ticket_id}/reply")
async def superadmin_support_reply(ticket_id: str, request: Request, content: str = Form(...), attachments: list[UploadFile] = File(default=[]), db: Session = Depends(get_db)):
    user, redirect = _require_superadmin(request, db)
    if redirect:
        return redirect
    ticket = db.query(SupportTicket).filter(SupportTicket.id == uuid.UUID(ticket_id)).first()
    if not ticket:
        return RedirectResponse("/app/superadmin/support?error=Ticket+not+found", status_code=303)
    try:
        message = add_message(db, ticket, user, content)
        add_attachments(db, ticket, message, user, attachments)
        db.commit()
        notify_ticket_parties(db, ticket, user, "New reply from platform support")
    except Exception as exc:
        db.rollback()
        return RedirectResponse(f"/app/superadmin/support/{ticket_id}?error={str(exc).replace(' ', '+')[:180]}", status_code=303)
    return RedirectResponse(f"/app/superadmin/support/{ticket_id}", status_code=303)


@router.post("/app/superadmin/support/{ticket_id}/status")
def superadmin_support_status(ticket_id: str, request: Request, new_status: str = Form(...), resolution: str = Form(""), priority: str = Form(""), db: Session = Depends(get_db)):
    user, redirect = _require_superadmin(request, db)
    if redirect:
        return redirect
    ticket = db.query(SupportTicket).filter(SupportTicket.id == uuid.UUID(ticket_id)).first()
    if not ticket:
        return RedirectResponse("/app/superadmin/support?error=Ticket+not+found", status_code=303)
    try:
        if priority:
            ticket.priority = TicketPriority(priority)
            ticket.updated_at = datetime.utcnow()
            add_audit = SupportAuditEvent(ticket_id=ticket.id, actor_id=user.id, event_type="priority_changed", details=f"Priority set to {priority}")
            db.add(add_audit)
        change_status(db, ticket, user, new_status, resolution)
        db.commit()
        notify_ticket_parties(db, ticket, user, f"Ticket status changed to {new_status.replace('_', ' ')}")
    except Exception as exc:
        db.rollback()
        return RedirectResponse(f"/app/superadmin/support/{ticket_id}?error={str(exc).replace(' ', '+')[:180]}", status_code=303)
    return RedirectResponse(f"/app/superadmin/support/{ticket_id}", status_code=303)


@router.post("/app/superadmin/support/{ticket_id}/note")
def superadmin_support_note(ticket_id: str, request: Request, content: str = Form(...), db: Session = Depends(get_db)):
    user, redirect = _require_superadmin(request, db)
    if redirect:
        return redirect
    ticket = db.query(SupportTicket).filter(SupportTicket.id == uuid.UUID(ticket_id)).first()
    if not ticket:
        return RedirectResponse("/app/superadmin/support?error=Ticket+not+found", status_code=303)
    try:
        add_message(db, ticket, user, content, is_internal=True)
        db.commit()
    except Exception as exc:
        db.rollback()
        return RedirectResponse(f"/app/superadmin/support/{ticket_id}?error={str(exc).replace(' ', '+')[:180]}", status_code=303)
    return RedirectResponse(f"/app/superadmin/support/{ticket_id}", status_code=303)


# ---- Notifications ----

@router.get("/app/notifications", response_class=HTMLResponse)
def notifications_page(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    blocked = _check_web_permission(db, user, "notifications", "/app/dashboard")
    if blocked:
        return blocked
    gym = db.query(Gym).filter(Gym.id == user.gym_id).first()
    return templates.TemplateResponse(request, "notifications.html", {
        "active_nav": "notifications",
        "gym_name": gym.name,
        "user_role": user.role.value,
        "result": None,
    })


@router.post("/app/notifications/renewal-reminders", response_class=HTMLResponse)
def send_renewal_reminders_web(request: Request, days: int = Form(7), db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect

    gym = db.query(Gym).filter(Gym.id == user.gym_id).first()
    cutoff = date.today() + timedelta(days=days)

    rows = (
        db.query(Payment, Member)
        .join(Member, Member.id == Payment.member_id)
        .filter(
            Payment.gym_id == user.gym_id,
            Payment.next_due_date.isnot(None),
            Payment.next_due_date <= cutoff,
            Payment.next_due_date >= date.today(),
        )
        .all()
    )

    sent, skipped, failed = 0, 0, 0
    for payment, member in rows:
        if not member.email:
            skipped += 1
            continue
        subject = f"Your membership at {gym.name} is renewing soon"
        body = (
            f"Hi {member.name},\n\nYour membership at {gym.name} is due for renewal on "
            f"{payment.next_due_date.isoformat()}. Please visit the front desk to renew.\n\n- {gym.name}"
        )
        if send_email(member.email, subject, body):
            sent += 1
        else:
            failed += 1

    return templates.TemplateResponse(request, "notifications.html", {
        "active_nav": "notifications",
        "gym_name": gym.name,
        "user_role": user.role.value,
        "result": {"sent": sent, "skipped_no_email": skipped, "failed": failed},
    })


@router.post("/app/notifications/inactivity-nudges", response_class=HTMLResponse)
def send_inactivity_nudges_web(request: Request, min_level: str = Form("medium"), db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect

    gym = db.query(Gym).filter(Gym.id == user.gym_id).first()
    level_order = {"low": 0, "medium": 1, "high": 2}
    threshold = level_order.get(min_level, 1)

    members = db.query(Member).filter(Member.gym_id == user.gym_id, Member.status == MemberStatus.ACTIVE).all()

    sent, skipped, failed = 0, 0, 0
    for member in members:
        risk = compute_churn_risk(db, user.gym_id, member)
        if level_order.get(risk["risk_level"], 0) < threshold:
            continue
        if not member.email:
            skipped += 1
            continue
        subject = f"We miss you at {gym.name}!"
        body = (
            f"Hi {member.name},\n\nWe noticed you haven't been in for a while. {risk['reason']}\n"
            f"Come back and see us soon!\n\n- {gym.name}"
        )
        if send_email(member.email, subject, body):
            sent += 1
        else:
            failed += 1

    return templates.TemplateResponse(request, "notifications.html", {
        "active_nav": "notifications",
        "gym_name": gym.name,
        "user_role": user.role.value,
        "result": {"sent": sent, "skipped_no_email": skipped, "failed": failed},
    })


# ---- Billing ----

@router.get("/app/billing", response_class=HTMLResponse)
def billing_page(request: Request, error: str = None, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect

    gym = db.query(Gym).filter(Gym.id == user.gym_id).first()
    plan = (
        db.query(PlatformPlan).filter(PlatformPlan.id == gym.platform_plan_id).first()
        if gym.platform_plan_id else None
    )
    plans = db.query(PlatformPlan).order_by(PlatformPlan.price).all()

    return templates.TemplateResponse(request, "billing.html", {
        "active_nav": "billing",
        "gym_name": gym.name,
        "user_role": user.role.value,
        "status": gym.subscription_status,
        "plan_name": plan.name if plan else None,
        "trial_ends_at": gym.trial_ends_at,
        "current_period_end": gym.current_period_end,
        "plans": plans,
        "error": error,
    })


@router.post("/app/billing/subscribe")
def subscribe_web(request: Request, platform_plan_id: str = Form(...), db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    if user.role != UserRole.GYM_OWNER:
        return RedirectResponse("/app/billing?error=Only+the+owner+can+change+the+plan", status_code=303)

    plan = db.query(PlatformPlan).filter(PlatformPlan.id == uuid.UUID(platform_plan_id)).first()
    if not plan:
        return RedirectResponse("/app/billing?error=Plan+not+found", status_code=303)

    gym = db.query(Gym).filter(Gym.id == user.gym_id).first()
    client = get_razorpay_client()

    if client is None:
        razorpay_subscription_id = f"sim_sub_{uuid.uuid4().hex[:12]}"
        status = "active"
    else:
        if not plan.razorpay_plan_id:
            return RedirectResponse("/app/billing?error=This+plan+has+no+Razorpay+plan+configured+yet", status_code=303)
        subscription = client.subscription.create({
            "plan_id": plan.razorpay_plan_id,
            "customer_notify": 1,
            "total_count": 120,
        })
        razorpay_subscription_id = subscription["id"]
        status = subscription["status"]

    gym.platform_plan_id = plan.id
    gym.razorpay_subscription_id = razorpay_subscription_id
    gym.subscription_status = status
    db.commit()

    return RedirectResponse("/app/billing", status_code=303)


def _require_superadmin(request: Request, db: Session):
    user = get_web_user(request, db)
    if not user or user.role != UserRole.SUPER_ADMIN:
        return None, RedirectResponse("/login", status_code=303)
    return user, None


def _delete_gym_record(db: Session, gym_id: uuid.UUID):
    db.query(ClassBooking).filter(ClassBooking.gym_id == gym_id).delete()
    db.query(Attendance).filter(Attendance.gym_id == gym_id).delete()
    db.query(Payment).filter(Payment.gym_id == gym_id).delete()
    db.query(Member).filter(Member.gym_id == gym_id).delete()
    db.query(MembershipPlan).filter(MembershipPlan.gym_id == gym_id).delete()
    db.query(GymClass).filter(GymClass.gym_id == gym_id).delete()
    db.query(User).filter(User.gym_id == gym_id).delete()
    gym = db.query(Gym).filter(Gym.id == gym_id).first()
    if gym:
        db.delete(gym)
    db.commit()


# ---- Staff & trainer management ----

@router.get("/app/staff", response_class=HTMLResponse)
def staff_page(request: Request, error: str = None, success: str = None, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    if user.role != UserRole.GYM_OWNER:
        return RedirectResponse("/app/dashboard?error=Only+the+owner+can+manage+staff", status_code=303)

    gym = db.query(Gym).filter(Gym.id == user.gym_id).first()
    staff = db.query(User).filter(
        User.gym_id == user.gym_id, User.role.in_([UserRole.STAFF, UserRole.TRAINER])
    ).order_by(User.created_at.desc()).all()
    permission_rows = []
    for member in staff:
        permission_rows.append({
            "user": member,
            "permissions": {key: has_permission(db, member, key) for key, _ in MANAGED_PERMISSIONS},
        })

    return templates.TemplateResponse(request, "staff.html", {
        "active_nav": "staff",
        "gym_name": gym.name,
        "user_role": user.role.value,
        "staff": staff,
        "error": error,
        "success": success,
        "permission_rows": permission_rows,
        "managed_permissions": MANAGED_PERMISSIONS,
    })


@router.post("/app/staff")
def create_staff_web(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    if user.role != UserRole.GYM_OWNER:
        return RedirectResponse("/app/dashboard?error=Only+the+owner+can+add+staff", status_code=303)

    if role not in ("staff", "trainer"):
        return RedirectResponse("/app/staff?error=Invalid+role", status_code=303)

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return RedirectResponse("/app/staff?error=Email+already+registered", status_code=303)

    new_user = User(
        gym_id=user.gym_id,
        email=email,
        hashed_password=hash_password(password),
        role=UserRole(role),
    )
    db.add(new_user)
    db.commit()
    gym = db.query(Gym).filter(Gym.id == user.gym_id).first()
    subject, body = build_staff_invitation_email(gym.name if gym else "Your gym", email.strip(), password, role)
    if not send_email(email.strip(), subject, body, is_html=True):
        return RedirectResponse("/app/staff?success=Account+created,+but+the+invitation+email+could+not+be+sent", status_code=303)
    return RedirectResponse("/app/staff?success=Invitation+sent+successfully", status_code=303)


@router.post("/app/staff/{staff_id}/permissions")
async def update_staff_permissions(staff_id: str, request: Request, db: Session = Depends(get_db)):
    owner, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    if owner.role != UserRole.GYM_OWNER:
        return RedirectResponse("/app/dashboard?error=Only+the+owner+can+manage+privileges", status_code=303)
    try:
        staff_uuid = uuid.UUID(staff_id)
    except ValueError:
        return RedirectResponse("/app/staff?error=Invalid+staff+id", status_code=303)
    staff_member = db.query(User).filter(
        User.id == staff_uuid, User.gym_id == owner.gym_id,
        User.role.in_([UserRole.STAFF, UserRole.TRAINER]),
    ).first()
    if not staff_member:
        return RedirectResponse("/app/staff?error=Staff+member+not+found", status_code=303)
    form = await request.form()
    for permission, _ in MANAGED_PERMISSIONS:
        record = db.query(UserPermission).filter(
            UserPermission.user_id == staff_member.id,
            UserPermission.permission == permission,
        ).first()
        allowed = permission in form
        if record:
            record.allowed = allowed
        else:
            db.add(UserPermission(user_id=staff_member.id, permission=permission, allowed=allowed))
    db.commit()
    return RedirectResponse("/app/staff?success=Privileges+updated", status_code=303)


@router.get("/app/activity", response_class=HTMLResponse)
def activity_history_page(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    if user.role != UserRole.GYM_OWNER:
        return RedirectResponse("/app/dashboard?error=Only+the+owner+can+view+activity+history", status_code=303)
    logs = db.query(ActivityLog).filter(ActivityLog.gym_id == user.gym_id).order_by(ActivityLog.created_at.desc()).limit(250).all()
    actors = {str(actor.id): actor.email for actor in db.query(User).filter(User.gym_id == user.gym_id).all()}
    return templates.TemplateResponse(request, "activity.html", {
        "active_nav": "activity",
        "gym_name": user.gym.name if user.gym else "Gym Console",
        "user_role": user.role.value,
        "logs": logs,
        "actors": actors,
    })


@router.post("/app/staff/{staff_id}/remove")
def remove_staff_web(staff_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    if user.role != UserRole.GYM_OWNER:
        return RedirectResponse("/app/dashboard?error=Only+the+owner+can+remove+staff", status_code=303)

    staff_member = db.query(User).filter(
        User.id == uuid.UUID(staff_id), User.gym_id == user.gym_id,
        User.role.in_([UserRole.STAFF, UserRole.TRAINER])
    ).first()
    if staff_member:
        db.delete(staff_member)
        db.commit()
    return RedirectResponse("/app/staff", status_code=303)


# ---- Attendance log ----

@router.post("/app/attendance/recognize")
async def recognize_attendance_web(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return JSONResponse({"status": "unauthorized", "detail": "Login required"}, status_code=401)

    payload = await request.json()
    image_data = payload.get("image", "") if isinstance(payload, dict) else ""
    if not image_data:
        return JSONResponse({"status": "error", "detail": "No image data provided"}, status_code=400)

    recognition_result = FaceRecognitionService.recognize_member(db, user.gym_id, image_data, FACE_MATCH_TOLERANCE)
    if recognition_result.get("status") in {"manual_only", "error", "no_face", "no_known_faces", "unknown"}:
        return JSONResponse(recognition_result)

    member = recognition_result["member"]
    try:
        _, action = _toggle_attendance_for_member(db, user.gym_id, member["member_id"])
    except ValueError:
        return JSONResponse({"status": "error", "detail": "Member not found"}, status_code=404)

    if action == "too_soon":
        return JSONResponse({
            "status": "too_soon",
            "detail": f"Checkout must be at least {CHECKOUT_MIN_GAP_MINUTES} minutes after check-in",
            "member_name": member["name"],
        })

    return JSONResponse({
        "status": action,
        "member_id": str(member["member_id"]),
        "member_name": member["name"],
        "time": datetime.now().strftime("%H:%M:%S"),
    })


@router.get("/app/attendance", response_class=HTMLResponse)
def attendance_log_page(request: Request, view: str = "recent", db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    blocked = _check_web_permission(db, user, "attendance", "/app/dashboard")
    if blocked:
        return blocked

    gym = db.query(Gym).filter(Gym.id == user.gym_id).first()
    today = date.today()

    query = db.query(Attendance, Member).join(Member, Member.id == Attendance.member_id).filter(
        Attendance.gym_id == user.gym_id
    )
    if view == "today":
        query = query.filter(Attendance.date == today)
    else:
        cutoff = today - timedelta(days=30)
        query = query.filter(Attendance.date >= cutoff)

    rows = query.order_by(Attendance.date.desc(), Attendance.check_in_time.desc()).all()
    records = [
        {"date": a.date, "check_in": a.check_in_time, "check_out": a.check_out_time, "member": m.name}
        for a, m in rows
    ]

    members = db.query(Member).filter(Member.gym_id == user.gym_id).order_by(Member.name).all()

    return templates.TemplateResponse(request, "attendance_log.html", {
        "active_nav": "attendance",
        "gym_name": gym.name,
        "user_role": user.role.value,
        "records": records,
        "view": view,
        "members": members,
        "error": None,
        "marked": None,
        "face_recognition_available": FaceRecognitionService.available(),
        "face_status_message": FaceRecognitionService.capability_message(),
    })


@router.post("/app/attendance/mark")
def mark_attendance_web(request: Request, member_id: str = Form(...), db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    blocked = _check_web_permission(db, user, "attendance", "/app/dashboard")
    if blocked:
        return blocked

    member = db.query(Member).filter(Member.id == uuid.UUID(member_id), Member.gym_id == user.gym_id).first()
    if not member:
        return RedirectResponse("/app/attendance?error=Member+not+found", status_code=303)

    today = date.today()
    from datetime import datetime as _dt
    now_str = _dt.now().strftime("%H:%M:%S")

    existing = db.query(Attendance).filter(
        Attendance.gym_id == user.gym_id,
        Attendance.member_id == member.id,
        Attendance.date == today,
    ).first()

    if existing is None:
        record = Attendance(
            gym_id=user.gym_id, member_id=member.id, date=today,
            check_in_time=now_str, status="present",
        )
        db.add(record)
        _log_activity(db, user, "member_checked_in", f"Checked in {member.name}")
        db.commit()
    elif existing.check_out_time is None:
        existing.check_out_time = now_str
        _log_activity(db, user, "member_checked_out", f"Checked out {member.name}")
        db.commit()

    return RedirectResponse("/app/attendance?view=today", status_code=303)


# ---- Class booking detail ----

@router.get("/app/classes/{class_id}", response_class=HTMLResponse)
def class_detail_page(class_id: str, request: Request, error: str = None, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect

    gym_class = db.query(GymClass).filter(
        GymClass.id == uuid.UUID(class_id), GymClass.gym_id == user.gym_id
    ).first()
    if not gym_class:
        return RedirectResponse("/app/classes?error=Class+not+found", status_code=303)

    gym = db.query(Gym).filter(Gym.id == user.gym_id).first()
    trainer = db.query(User).filter(User.id == gym_class.trainer_id).first() if gym_class.trainer_id else None

    bookings = (
        db.query(ClassBooking, Member)
        .join(Member, Member.id == ClassBooking.member_id)
        .filter(ClassBooking.class_id == gym_class.id)
        .all()
    )
    booking_rows = [{"member_id": m.id, "member_name": m.name} for b, m in bookings]

    return templates.TemplateResponse(request, "class_detail.html", {
        "active_nav": "classes",
        "gym_name": gym.name,
        "user_role": user.role.value,
        "gym_class": {
            "id": gym_class.id, "name": gym_class.name,
            "day": DAY_NAMES[gym_class.day_of_week], "time": gym_class.start_time,
            "duration": gym_class.duration_minutes, "capacity": gym_class.capacity,
            "trainer": trainer.email if trainer else "Unassigned",
        },
        "bookings": booking_rows,
        "error": error,
    })


@router.post("/app/classes/{class_id}/bookings/{member_id}/cancel")
def cancel_booking_web(class_id: str, member_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect

    booking = db.query(ClassBooking).filter(
        ClassBooking.class_id == uuid.UUID(class_id),
        ClassBooking.member_id == uuid.UUID(member_id),
        ClassBooking.gym_id == user.gym_id,
    ).first()
    if booking:
        db.delete(booking)
        db.commit()

    return RedirectResponse(f"/app/classes/{class_id}", status_code=303)


# ---- Inquiries (leads & follow-ups) ----

@router.get('/app/inquiries', response_class=HTMLResponse)
def inquiries_page(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    blocked = _check_web_permission(db, user, "inquiries", "/app/dashboard")
    if blocked:
        return blocked

    plans = db.query(MembershipPlan).filter(MembershipPlan.gym_id == user.gym_id).order_by(MembershipPlan.price).all()
    from app.models.inquiry import Inquiry
    inquiry_rows = db.query(Inquiry).filter(Inquiry.gym_id == user.gym_id).order_by(Inquiry.next_followup.asc().nulls_last(), Inquiry.created_at.desc()).all()
    rows = []
    from datetime import date
    for iq in inquiry_rows:
        rows.append({
            'id': iq.id,
            'name': iq.name,
            'contact': iq.contact,
            'plan_name': iq.plan.name if iq.plan else None,
            'next_followup': iq.next_followup,
            'status': iq.status,
        })

    return templates.TemplateResponse(request, 'inquiries.html', {
        'active_nav': 'inquiries',
        'gym_name': db.query(Gym).filter(Gym.id == user.gym_id).first().name,
        'user_role': user.role.value,
        'plans': plans,
        'inquiries': rows,
        'now_date': date.today(),
    })


@router.post('/app/inquiries')
def create_inquiry(request: Request,
                   name: str = Form(...),
                   contact: str = Form(''),
                   email: str = Form(''),
                   source: str = Form('walk-in'),
                   plan_id: str = Form(''),
                   next_followup: str = Form(''),
                   db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    blocked = _check_web_permission(db, user, "inquiries", "/app/dashboard")
    if blocked:
        return blocked

    from app.models.inquiry import Inquiry
    iq = Inquiry(
        gym_id=user.gym_id,
        name=name.strip(),
        contact=contact.strip() or None,
        email=email.strip() or None,
        source=source or None,
    )
    if plan_id:
        try:
            import uuid as _u
            iq.interested_plan_id = _u.UUID(plan_id)
        except Exception:
            pass
    if next_followup:
        try:
            from datetime import datetime
            iq.next_followup = datetime.strptime(next_followup, '%Y-%m-%d').date()
            iq.status = iq.status.__class__.SCHEDULED if iq.next_followup else iq.status
        except Exception:
            pass
    db.add(iq)
    _log_activity(db, user, "inquiry_created", f"Added inquiry {name.strip()}")
    db.commit()
    return RedirectResponse('/app/inquiries', status_code=303)


@router.get('/app/inquiries/{inquiry_id}', response_class=HTMLResponse)
def inquiry_detail(inquiry_id: str, request: Request, error: str = None, success: str = None, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    from app.models.inquiry import Inquiry
    import uuid as _u
    try:
        iq = db.query(Inquiry).filter(Inquiry.id == _u.UUID(inquiry_id), Inquiry.gym_id == user.gym_id).first()
    except Exception:
        return RedirectResponse('/app/inquiries?error=Invalid+id', status_code=303)
    if not iq:
        return RedirectResponse('/app/inquiries?error=Inquiry+not+found', status_code=303)

    plan_name = iq.plan.name if iq.plan else None
    return templates.TemplateResponse(request, 'inquiry_detail.html', {
        'active_nav': 'members',
        'gym_name': db.query(Gym).filter(Gym.id == user.gym_id).first().name,
        'user_role': user.role.value,
        'inquiry': iq,
        'plan_name': plan_name,
        'error': error,
        'success': success,
    })


@router.post('/app/inquiries/{inquiry_id}/send-reminder')
def send_inquiry_reminder(inquiry_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    blocked = _check_web_permission(db, user, "inquiries", "/app/dashboard")
    if blocked:
        return blocked
    from app.models.inquiry import FollowUp, Inquiry
    import uuid as _u
    try:
        inquiry = db.query(Inquiry).filter(Inquiry.id == _u.UUID(inquiry_id), Inquiry.gym_id == user.gym_id).first()
    except Exception:
        return RedirectResponse('/app/inquiries?error=Invalid+id', status_code=303)
    if not inquiry:
        return RedirectResponse('/app/inquiries?error=Inquiry+not+found', status_code=303)

    recipient = inquiry.email.strip() if inquiry.email else None
    if not recipient:
        return RedirectResponse(f'/app/inquiries/{inquiry_id}?error=No+lead+email+available+for+this+inquiry', status_code=303)

    owner = db.query(User).filter(User.gym_id == inquiry.gym_id, User.role == UserRole.GYM_OWNER).first()
    cc_emails = [owner.email] if owner and owner.email and owner.email.lower() != recipient.lower() else []

    gym_name = db.query(Gym).filter(Gym.id == inquiry.gym_id).first().name if db.query(Gym).filter(Gym.id == inquiry.gym_id).first() else 'Your gym'
    subject, body = _build_inquiry_reminder_email(inquiry, inquiry.name, gym_name)
    sent = send_email(recipient, subject, body, is_html=True, cc_emails=cc_emails)
    if not sent:
        return RedirectResponse(f'/app/inquiries/{inquiry_id}?error=Reminder+email+could+not+be+sent', status_code=303)

    inquiry.last_reminded = date.today()
    db.add(FollowUp(
        inquiry_id=inquiry.id,
        staff_id=user.id,
        note="Reminder email sent successfully",
        outcome="email_sent",
    ))
    _log_activity(db, user, "inquiry_reminder_sent", f"Sent reminder for {inquiry.name}")
    db.add(inquiry)
    db.commit()
    return RedirectResponse(f'/app/inquiries/{inquiry_id}?success=Reminder+email+sent+successfully', status_code=303)


@router.post('/app/inquiries/{inquiry_id}/followups')
def add_followup(inquiry_id: str, request: Request, note: str = Form(''), outcome: str = Form(''), next_date: str = Form(''), db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    blocked = _check_web_permission(db, user, "inquiries", "/app/dashboard")
    if blocked:
        return blocked
    from app.models.inquiry import FollowUp, Inquiry
    import uuid as _u
    try:
        iq = db.query(Inquiry).filter(Inquiry.id == _u.UUID(inquiry_id), Inquiry.gym_id == user.gym_id).first()
    except Exception:
        return RedirectResponse('/app/inquiries?error=Invalid+id', status_code=303)
    if not iq:
        return RedirectResponse('/app/inquiries?error=Inquiry+not+found', status_code=303)

    fu = FollowUp(inquiry_id=iq.id, staff_id=user.id if user else None, note=note.strip() or None, outcome=outcome.strip() or None)
    if next_date:
        try:
            from datetime import datetime
            fu.next_date = datetime.strptime(next_date, '%Y-%m-%d').date()
            iq.next_followup = fu.next_date
            iq.status = iq.status.__class__.SCHEDULED
        except Exception:
            pass
    db.add(fu)
    _log_activity(db, user, "followup_added", f"Added follow-up for {iq.name}")
    db.add(iq)
    db.commit()
    return RedirectResponse(f'/app/inquiries/{inquiry_id}', status_code=303)


@router.post('/app/inquiries/{inquiry_id}/convert')
def convert_inquiry(inquiry_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    from app.models.inquiry import Inquiry
    from app.models.member import Member
    import uuid as _u
    try:
        iq = db.query(Inquiry).filter(Inquiry.id == _u.UUID(inquiry_id), Inquiry.gym_id == user.gym_id).first()
    except Exception:
        return RedirectResponse('/app/inquiries?error=Invalid+id', status_code=303)
    if not iq:
        return RedirectResponse('/app/inquiries?error=Inquiry+not+found', status_code=303)

    # create member pre-filled
    member = Member(gym_id=user.gym_id, name=iq.name, contact=iq.contact or None, email=iq.email or None, plan_id=iq.interested_plan_id)
    db.add(member)
    iq.status = iq.status.__class__.CONVERTED
    db.add(iq)
    db.commit()
    return RedirectResponse(f'/app/members/{member.id}', status_code=303)


@router.post('/app/inquiries/{inquiry_id}/mark-lost')
def mark_lost(inquiry_id: str, request: Request, lost_reason: str = Form(''), db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect
    from app.models.inquiry import Inquiry, FollowUp
    import uuid as _u
    try:
        iq = db.query(Inquiry).filter(Inquiry.id == _u.UUID(inquiry_id), Inquiry.gym_id == user.gym_id).first()
    except Exception:
        return RedirectResponse('/app/inquiries?error=Invalid+id', status_code=303)
    if not iq:
        return RedirectResponse('/app/inquiries?error=Inquiry+not+found', status_code=303)

    iq.status = iq.status.__class__.LOST
    if lost_reason:
        fu = FollowUp(inquiry_id=iq.id, staff_id=user.id if user else None, note=f'Lost: {lost_reason}', outcome='lost')
        db.add(fu)
    db.add(iq)
    db.commit()
    return RedirectResponse('/app/inquiries', status_code=303)


# ---- Super-admin console ----

@router.get("/app/superadmin", response_class=HTMLResponse)
def superadmin_dashboard(
    request: Request,
    section: str = "overview",
    edit_gym: str = "",
    edit_plan: str = "",
    error: str = None,
    success: str = None,
    db: Session = Depends(get_db),
):
    user, redirect = _require_superadmin(request, db)
    if redirect:
        return redirect

    gyms = db.query(Gym).order_by(Gym.created_at.desc()).all()
    plans = db.query(PlatformPlan).order_by(PlatformPlan.price).all()
    plan_map = {p.id: p for p in plans}

    total_members = db.query(Member).count()
    total_platform_plans = len(plans)
    active_members = db.query(Member).filter(Member.status == MemberStatus.ACTIVE).count()
    expired_members = db.query(Member).filter(Member.status == MemberStatus.EXPIRED).count()
    frozen_members = db.query(Member).filter(Member.status == MemberStatus.FROZEN).count()
    total_users = db.query(User).filter(User.role != UserRole.SUPER_ADMIN).count()
    total_attendance = db.query(Attendance).count()
    today_attendance = db.query(Attendance).filter(Attendance.date == date.today()).count()
    month_start = date.today().replace(day=1)
    monthly_payments = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.payment_date >= month_start
    ).scalar()
    total_payments = db.query(func.coalesce(func.sum(Payment.amount), 0)).scalar()

    gym_rows = []
    active_count = 0
    trial_count = 0
    mrr = 0.0
    for g in gyms:
        member_count = db.query(Member).filter(Member.gym_id == g.id).count()
        owner = db.query(User).filter(User.gym_id == g.id, User.role == UserRole.GYM_OWNER).first()
        plan = plan_map.get(g.platform_plan_id)
        if g.subscription_status == "active":
            active_count += 1
            if plan:
                mrr += float(plan.price)
        elif g.subscription_status == "trial":
            trial_count += 1
        gym_rows.append({
            "id": g.id,
            "name": g.name,
            "status": g.subscription_status,
            "plan_id": str(g.platform_plan_id) if g.platform_plan_id else "",
            "plan_name": plan.name if plan else None,
            "owner_email": owner.email if owner else "",
            "member_count": member_count,
            "created_at": g.created_at.date(),
        })

    plan_rows = []
    for plan in plans:
        plan_rows.append({
            "id": plan.id,
            "name": plan.name,
            "price": plan.price,
            "billing_interval": plan.billing_interval,
            "member_limit": plan.member_limit,
            "gym_count": db.query(Gym).filter(Gym.platform_plan_id == plan.id).count(),
            "member_count": db.query(Member).join(Gym, Member.gym_id == Gym.id).filter(Gym.platform_plan_id == plan.id).count(),
        })

    status_counts = {
        "active": active_count,
        "trial": trial_count,
        "cancelled": sum(1 for gym in gyms if gym.subscription_status == "cancelled"),
        "past_due": sum(1 for gym in gyms if gym.subscription_status == "past_due"),
    }
    valid_sections = {"overview", "analytics", "gyms", "plans", "settings"}
    active_section = section if section in valid_sections else "overview"
    edit_gym_id = edit_gym if any(str(g.id) == edit_gym for g in gyms) else ""
    edit_plan_id = edit_plan if any(str(plan.id) == edit_plan for plan in plans) else ""

    # load reminder time from DB
    try:
       from app.core.settings_db import ensure_table, get_setting
       ensure_table()
       reminder_time = get_setting('followup_reminder_time')
    except Exception:
       reminder_time = None

    return templates.TemplateResponse(request, "superadmin_dashboard.html", {
        "active_section": active_section,
        "edit_gym_id": edit_gym_id,
        "edit_plan_id": edit_plan_id,
        "total_gyms": len(gyms),
        "total_members": total_members,
        "active_members": active_members,
        "expired_members": expired_members,
        "frozen_members": frozen_members,
        "total_users": total_users,
        "total_attendance": total_attendance,
        "today_attendance": today_attendance,
        "monthly_payments": monthly_payments,
        "total_payments": total_payments,
        "total_platform_plans": total_platform_plans,
        "active_count": active_count,
        "trial_count": trial_count,
        "mrr": mrr,
        "gyms": gym_rows,
        "plans": plans,
        "plan_rows": plan_rows,
        "status_counts": status_counts,
        "error": error,
        "success": success,
        "user_role": user.role.value,
        "smtp_from_email": settings.from_email or settings.smtp_user,
        "smtp_configured": bool(settings.smtp_host and settings.smtp_user and settings.smtp_password),
        "reminder_time": reminder_time,
    })


@router.post("/app/superadmin/test-email")
def test_superadmin_email(
    request: Request,
    email: str = Form(...),
    subject: str = Form("Gym SaaS SMTP verification"),
    body: str = Form("This is a test email from the Gym SaaS platform."),
    db: Session = Depends(get_db),
):
    user, redirect = _require_superadmin(request, db)
    if redirect:
        return redirect

    if not email.strip():
        return RedirectResponse("/app/superadmin?error=Recipient+email+required", status_code=303)

    try:
        sent = send_email(email.strip(), subject.strip() or "Gym SaaS SMTP verification", body.strip() or "This is a test email from the Gym SaaS platform.")
        if sent:
            return RedirectResponse("/app/superadmin?success=Test+email+sent+successfully", status_code=303)
        return RedirectResponse("/app/superadmin?error=Test+email+failed.+Check+SMTP+settings+and+verified+sender.", status_code=303)
    except Exception as exc:
        return RedirectResponse(f"/app/superadmin?error=SMTP+error%3A+{str(exc).replace(' ', '+')}", status_code=303)


@router.post('/app/superadmin/set-reminder-time')
def set_reminder_time(request: Request, reminder_time: str = Form(''), db: Session = Depends(get_db)):
        user, redirect = _require_superadmin(request, db)
        if redirect:
            return redirect

        if not reminder_time or not reminder_time.strip():
            return RedirectResponse('/app/superadmin?error=Invalid+time', status_code=303)

        # basic validation HH:MM
        try:
            parts = reminder_time.strip().split(':')
            h = int(parts[0]); m = int(parts[1])
            if not (0 <= h < 24 and 0 <= m < 60):
                raise ValueError()
        except Exception:
            return RedirectResponse('/app/superadmin?error=Invalid+time+format+expected+HH:MM', status_code=303)

        try:
            from app.core.settings_db import ensure_table, set_setting
            ensure_table()
            set_setting('followup_reminder_time', f"{h:02d}:{m:02d}")
            return RedirectResponse('/app/superadmin?success=Reminder+time+updated', status_code=303)
        except Exception as exc:
            return RedirectResponse(f'/app/superadmin?error=Failed+to+save+setting+{str(exc)}', status_code=303)

@router.post('/app/superadmin/run-followup-reminders')
def run_followup_reminders(request: Request, db: Session = Depends(get_db)):
    """Manual endpoint for superadmin to trigger follow-up reminder job (useful when scheduler is disabled)."""
    user, redirect = _require_superadmin(request, db)
    if redirect:
        return redirect

    from datetime import date, timedelta
    from app.models.inquiry import Inquiry
    sent_count = 0
    today = date.today()
    tomorrow = today + timedelta(days=1)

    rows = (
        db.query(Inquiry)
        .filter(Inquiry.next_followup == tomorrow, Inquiry.status != Inquiry.status.type.enum_class.CONVERTED, Inquiry.status != Inquiry.status.type.enum_class.LOST)
        .all()
    )

    for inquiry in rows:
        recipient = inquiry.email.strip() if inquiry.email else None
        if not recipient:
            continue

        owner = db.query(User).filter(User.gym_id == inquiry.gym_id, User.role == UserRole.GYM_OWNER).first()
        cc_emails = [owner.email] if owner and owner.email and owner.email.lower() != recipient.lower() else []

        gym_name = db.query(Gym).filter(Gym.id == inquiry.gym_id).first().name if db.query(Gym).filter(Gym.id == inquiry.gym_id).first() else 'Your gym'
        subject, body = _build_inquiry_reminder_email(inquiry, inquiry.name, gym_name)
        try:
            send_email(recipient, subject, body, is_html=True, cc_emails=cc_emails)
            inquiry.last_reminded = date.today()
            db.add(inquiry)
            db.commit()
            sent_count += 1
        except Exception:
            db.rollback()

    return JSONResponse({'sent': sent_count, 'candidates': len(rows)})


@router.post("/app/superadmin/platform-plans")
def create_platform_plan_web(
    request: Request,
    name: str = Form(...),
    price: str = Form(...),
    billing_interval: str = Form("monthly"),
    member_limit: str = Form(""),
    razorpay_plan_id: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = _require_superadmin(request, db)
    if redirect:
        return redirect

    if not name.strip():
        return RedirectResponse("/app/superadmin?error=Plan+name+required", status_code=303)

    try:
        parsed_price = float(price)
    except ValueError:
        return RedirectResponse("/app/superadmin?error=Invalid+plan+price", status_code=303)

    member_limit_value = None
    if member_limit.strip():
        try:
            member_limit_value = int(member_limit)
            if member_limit_value <= 0:
                raise ValueError
        except ValueError:
            return RedirectResponse("/app/superadmin?error=Member+limit+must+be+a+positive+integer", status_code=303)

    existing = db.query(PlatformPlan).filter(PlatformPlan.name == name.strip()).first()
    if existing:
        return RedirectResponse("/app/superadmin?error=Platform+plan+already+exists", status_code=303)

    plan = PlatformPlan(
        name=name.strip(),
        price=parsed_price,
        billing_interval=billing_interval or "monthly",
        member_limit=member_limit_value,
        razorpay_plan_id=razorpay_plan_id.strip() or None,
    )
    db.add(plan)
    db.commit()
    return RedirectResponse("/app/superadmin?success=Platform+plan+created+successfully", status_code=303)


@router.post("/app/superadmin/platform-plans/{plan_id}/update")
def update_platform_plan_web(
    plan_id: str,
    request: Request,
    name: str = Form(...),
    price: str = Form(...),
    billing_interval: str = Form("monthly"),
    member_limit: str = Form(""),
    razorpay_plan_id: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = _require_superadmin(request, db)
    if redirect:
        return redirect

    try:
        plan_uuid = uuid.UUID(plan_id)
    except ValueError:
        return RedirectResponse("/app/superadmin?error=Invalid+plan+id", status_code=303)

    plan = db.query(PlatformPlan).filter(PlatformPlan.id == plan_uuid).first()
    if not plan:
        return RedirectResponse("/app/superadmin?error=Platform+plan+not+found", status_code=303)

    try:
        plan.price = float(price)
    except ValueError:
        return RedirectResponse("/app/superadmin?error=Invalid+plan+price", status_code=303)

    requested_name = name.strip() or plan.name
    if db.query(PlatformPlan).filter(PlatformPlan.name == requested_name, PlatformPlan.id != plan.id).first():
        return RedirectResponse("/app/superadmin?error=Platform+plan+already+exists", status_code=303)

    plan.name = requested_name
    plan.billing_interval = billing_interval or "monthly"
    plan.member_limit = int(member_limit) if member_limit and member_limit.strip() else None
    plan.razorpay_plan_id = razorpay_plan_id.strip() or None
    db.commit()
    return RedirectResponse("/app/superadmin?success=Platform+plan+updated+successfully", status_code=303)


@router.post("/app/superadmin/platform-plans/{plan_id}/delete")
def delete_platform_plan_web(plan_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_superadmin(request, db)
    if redirect:
        return redirect

    try:
        plan_uuid = uuid.UUID(plan_id)
    except ValueError:
        return RedirectResponse("/app/superadmin?error=Invalid+plan+id", status_code=303)

    plan = db.query(PlatformPlan).filter(PlatformPlan.id == plan_uuid).first()
    if not plan:
        return RedirectResponse("/app/superadmin?error=Platform+plan+not+found", status_code=303)

    linked_gyms = db.query(Gym).filter(Gym.platform_plan_id == plan.id).count()
    if linked_gyms:
        return RedirectResponse(
            "/app/superadmin?section=plans&error=Unassign+this+plan+from+all+gyms+before+deleting+it",
            status_code=303,
        )
    db.delete(plan)
    db.commit()
    return RedirectResponse("/app/superadmin?success=Platform+plan+deleted+successfully", status_code=303)


@router.post("/app/superadmin/gyms")
def create_gym_web(
    request: Request,
    name: str = Form(...),
    owner_email: str = Form(...),
    owner_password: str = Form(...),
    platform_plan_id: str = Form(""),
    subscription_status: str = Form("trial"),
    db: Session = Depends(get_db),
):
    user, redirect = _require_superadmin(request, db)
    if redirect:
        return redirect

    if not name.strip() or not owner_email.strip() or not owner_password:
        return RedirectResponse("/app/superadmin?error=Please+fill+all+gym+details", status_code=303)

    if not platform_plan_id:
        return RedirectResponse("/app/superadmin?error=Platform+plan+is+required+for+every+gym", status_code=303)

    if db.query(User).filter(User.email == owner_email.strip()).first():
        return RedirectResponse("/app/superadmin?error=Email+already+registered", status_code=303)

    plan = None
    if platform_plan_id:
        try:
            plan = db.query(PlatformPlan).filter(PlatformPlan.id == uuid.UUID(platform_plan_id)).first()
        except ValueError:
            return RedirectResponse("/app/superadmin?error=Invalid+plan+selected", status_code=303)
        if not plan:
            return RedirectResponse("/app/superadmin?error=Plan+not+found", status_code=303)

    status = subscription_status if subscription_status in {"trial", "active", "cancelled", "past_due"} else "trial"
    gym = Gym(
        name=name.strip(),
        subscription_status=status,
        platform_plan_id=plan.id if plan else None,
        trial_ends_at=(date.today() + timedelta(days=14)) if status == "trial" else None,
    )
    db.add(gym)
    db.flush()

    owner = User(
        gym_id=gym.id,
        email=owner_email.strip(),
        hashed_password=hash_password(owner_password),
        role=UserRole.GYM_OWNER,
    )
    db.add(owner)
    db.commit()
    subject, body = build_gym_owner_welcome_email(
        gym.name,
        owner.email,
        owner_password,
        settings.public_url.rstrip("/") + "/login" if settings.public_url else "",
    )
    if not send_email(owner.email, subject, body, is_html=True):
        return RedirectResponse(
            "/app/superadmin?success=Gym+created,+but+the+owner+welcome+email+could+not+be+sent",
            status_code=303,
        )
    return RedirectResponse("/app/superadmin?success=Gym+created+and+owner+welcome+email+sent", status_code=303)


@router.post("/app/superadmin/gyms/{gym_id}/update")
def update_gym_web(
    gym_id: str,
    request: Request,
    name: str = Form(...),
    owner_email: str = Form(""),
    owner_password: str = Form(""),
    platform_plan_id: str = Form(""),
    subscription_status: str = Form("trial"),
    db: Session = Depends(get_db),
):
    user, redirect = _require_superadmin(request, db)
    if redirect:
        return redirect

    try:
        gym_uuid = uuid.UUID(gym_id)
    except ValueError:
        return RedirectResponse("/app/superadmin?error=Invalid+gym+id", status_code=303)

    gym = db.query(Gym).filter(Gym.id == gym_uuid).first()
    if not gym:
        return RedirectResponse("/app/superadmin?error=Gym+not+found", status_code=303)

    if not platform_plan_id:
        return RedirectResponse("/app/superadmin?error=Platform+plan+is+required+for+every+gym", status_code=303)

    plan = None
    if platform_plan_id:
        try:
            plan = db.query(PlatformPlan).filter(PlatformPlan.id == uuid.UUID(platform_plan_id)).first()
        except ValueError:
            return RedirectResponse("/app/superadmin?error=Invalid+plan+selected", status_code=303)
        if not plan:
            return RedirectResponse("/app/superadmin?error=Plan+not+found", status_code=303)

    gym.name = name.strip() or gym.name
    gym.platform_plan_id = plan.id if plan else None
    gym.subscription_status = subscription_status if subscription_status in {"trial", "active", "cancelled", "past_due"} else gym.subscription_status
    if gym.subscription_status == "trial" and not gym.trial_ends_at:
        gym.trial_ends_at = date.today() + timedelta(days=14)

    if owner_email and owner_email.strip():
        normalized_email = owner_email.strip()
        owner = db.query(User).filter(User.gym_id == gym.id, User.role == UserRole.GYM_OWNER).first()
        if owner is None:
            owner = User(gym_id=gym.id, email=normalized_email, hashed_password=hash_password(owner_password or "gymowner123"), role=UserRole.GYM_OWNER)
            db.add(owner)
        else:
            existing_user = db.query(User).filter(User.email == normalized_email, User.id != owner.id).first()
            if existing_user:
                return RedirectResponse("/app/superadmin?error=Email+already+registered", status_code=303)
            owner.email = normalized_email
            if owner_password and owner_password.strip():
                owner.hashed_password = hash_password(owner_password.strip())

    db.commit()
    return RedirectResponse("/app/superadmin?success=Gym+updated+successfully", status_code=303)


@router.post("/app/superadmin/gyms/{gym_id}/delete")
def delete_gym_web(gym_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_superadmin(request, db)
    if redirect:
        return redirect

    try:
        gym_uuid = uuid.UUID(gym_id)
    except ValueError:
        return RedirectResponse("/app/superadmin?error=Invalid+gym+id", status_code=303)

    _delete_gym_record(db, gym_uuid)
    return RedirectResponse("/app/superadmin?success=Gym+deleted+successfully", status_code=303)


# ---- Member photo (upload from the console, used by the kiosk for recognition) ----

@router.post("/app/members/{member_id}/photo")
async def upload_member_photo_web(
    member_id: str,
    request: Request,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect

    member = db.query(Member).filter(Member.id == uuid.UUID(member_id), Member.gym_id == user.gym_id).first()
    if not member:
        return RedirectResponse("/app/members?error=Member+not+found", status_code=303)

    extension = photo.filename.split(".")[-1] if "." in photo.filename else "jpg"
    contents = await photo.read()
    path = save_member_photo(str(user.gym_id), str(member.id), contents, extension)
    member.photo_path = path
    db.commit()

    return RedirectResponse(f"/app/members/{member_id}", status_code=303)


@router.get("/app/members/{member_id}/photo")
def get_member_photo_web(member_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_gym_user(request, db)
    if redirect:
        return redirect

    member = db.query(Member).filter(Member.id == uuid.UUID(member_id), Member.gym_id == user.gym_id).first()
    if not member or not member_photo_exists(member.photo_path):
        return RedirectResponse(f"/app/members/{member_id}?error=No+photo+uploaded", status_code=303)

    return StreamingResponse(iter([get_member_photo(member.photo_path)]), media_type=member_photo_content_type(member.photo_path))
