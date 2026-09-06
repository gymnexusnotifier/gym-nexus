from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.database import Base, SessionLocal, engine
from sqlalchemy import inspect, text
from app.core.email import send_email
from app.core.security import hash_password
from app.core.security import decode_access_token
from app.core.config import settings
from app.core.mongodb import close_mongodb, initialize_mongodb, mongo_health
from app.models.enums import UserRole
from app.models.gym import Gym
from app.models.user import User
from app.models.activity_log import ActivityLog
from app.models.user_permission import UserPermission
from app.models.attendance import Attendance
from app.models.gym_class import GymClass, ClassBooking
from app.models.inquiry import Inquiry, FollowUp
from app.models.member import Member, MembershipPlan
from app.models.payment import Payment
from app.models.platform_plan import PlatformPlan
from app.models.support import SupportTicket, SupportMessage, SupportAttachment, SupportAuditEvent
from app.routers import auth, members, users, attendance, payments, dashboard, churn, classes, notifications, billing, web, support

Base.metadata.create_all(bind=engine)
print(f"Database schema check: {len(Base.metadata.tables)} tables registered")


def ensure_payment_columns() -> None:
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("payments")}
    statements = []
    if "payment_method" not in columns:
        statements.append("ALTER TABLE payments ADD COLUMN payment_method VARCHAR NOT NULL DEFAULT 'cash'")
    if "transaction_id" not in columns:
        statements.append("ALTER TABLE payments ADD COLUMN transaction_id VARCHAR")
    if statements:
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))


ensure_payment_columns()

DEFAULT_SUPERADMIN_EMAIL = "faisal.khalik.khan@gmail.com"
DEFAULT_SUPERADMIN_PASSWORD = "Uzma#2025"
DEFAULT_SUPERADMIN_NAME = "Nexus-Admin"


def ensure_default_superadmin() -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == DEFAULT_SUPERADMIN_EMAIL).first()
        if user is not None:
            return

        db.add(
            User(
                gym_id=None,
                email=DEFAULT_SUPERADMIN_EMAIL,
                hashed_password=hash_password(DEFAULT_SUPERADMIN_PASSWORD),
                role=UserRole.SUPER_ADMIN,
            )
        )
        db.commit()

        send_email(
            DEFAULT_SUPERADMIN_EMAIL,
            "Your Nexus-Admin gym SaaS account is ready",
            (
                f"Name: {DEFAULT_SUPERADMIN_NAME}\n"
                f"Email: {DEFAULT_SUPERADMIN_EMAIL}\n"
                f"Password: {DEFAULT_SUPERADMIN_PASSWORD}\n\n"
                "Use this to log in to the platform dashboard."
            ),
        )
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.db_backend == "mongo":
        initialize_mongodb()
        print(f"MongoDB connection ready: database={settings.mongodb_database}")

    # create default superadmin and then start background scheduler
    ensure_default_superadmin()

    # start APScheduler job for inquiry follow-up reminders (guarded)
    if settings.brevo_api_key and (settings.from_email or settings.smtp_user):
        email_transport = "Brevo HTTPS API"
    elif settings.brevo_api_key:
        email_transport = "Not configured: BREVO_API_KEY exists but FROM_EMAIL is missing"
    elif settings.from_email or settings.smtp_user:
        email_transport = "SMTP fallback: BREVO_API_KEY is missing"
    else:
        email_transport = "Not configured: BREVO_API_KEY and FROM_EMAIL are missing"
    print(f"Email transport: {email_transport}")
    print(
        "Email variable check: "
        f"BREVO_API_KEY={'set' if settings.brevo_api_key else 'missing'}, "
        f"FROM_EMAIL={'set' if settings.from_email else 'missing'}, "
        f"SMTP_HOST={'set' if settings.smtp_host else 'missing'}, "
        f"SMTP_PORT={settings.smtp_port}"
    )

    scheduler = None
    if not settings.__dict__.get('scheduler_enabled', True):
        print('Scheduler disabled by settings.scheduler_enabled')
    else:
        import importlib, sys
        found_aps = importlib.util.find_spec('apscheduler') is not None
        found_pytz = importlib.util.find_spec('pytz') is not None
        print(f"Scheduler diagnostic: apscheduler found={found_aps}, pytz found={found_pytz}, python={sys.executable}")

        if not found_aps or not found_pytz:
            print('APSscheduler or pytz not available in this Python environment. Scheduler will be disabled.')
            print('Install with: pip install -r requirements.txt OR run the app with the same Python that has these packages installed.')
        else:
            try:
                from datetime import datetime, time, timedelta
                from apscheduler.schedulers.asyncio import AsyncIOScheduler
                from apscheduler.triggers.cron import CronTrigger
                from app.core.database import SessionLocal
                from app.models.inquiry import Inquiry
                from app.core.email import send_email
                import pytz

                scheduler = AsyncIOScheduler(timezone=pytz.UTC)

                def _is_reminder_time_due(now_utc, cfg_time: str | None) -> bool:
                    if not cfg_time or not cfg_time.strip():
                        return True
                    try:
                        h, m = map(int, cfg_time.strip().split(':', 1))
                        return (now_utc.hour, now_utc.minute) >= (h, m)
                    except Exception:
                        return True

                def _build_inquiry_reminder_email(inquiry, recipient_name: str | None = None, gym_name: str | None = None):
                    return web._build_inquiry_reminder_email(inquiry, recipient_name, gym_name)

                def followup_reminder_job():
                    db = SessionLocal()
                    try:
                        from datetime import date, timedelta, datetime as _dt
                        today = date.today()
                        tomorrow = today + timedelta(days=1)

                        try:
                            from app.core.settings_db import ensure_table, get_setting
                            ensure_table()
                            cfg_time = get_setting('followup_reminder_time', '08:00') or '08:00'
                        except Exception:
                            cfg_time = '08:00'

                        now_utc = _dt.utcnow()
                        if not _is_reminder_time_due(now_utc, cfg_time):
                            return

                        rows = (
                            db.query(Inquiry)
                            .filter(
                                Inquiry.next_followup == tomorrow,
                                Inquiry.status != Inquiry.status.type.enum_class.CONVERTED,
                                Inquiry.status != Inquiry.status.type.enum_class.LOST,
                                Inquiry.last_reminded != today,
                            )
                            .all()
                        )

                        for inquiry in rows:
                            recipient = inquiry.email.strip() if inquiry.email else None
                            if not recipient:
                                continue

                            owner = db.query(User).filter(User.gym_id == inquiry.gym_id, User.role == UserRole.GYM_OWNER).first()
                            cc_emails = [owner.email] if owner and owner.email and owner.email.lower() != recipient.lower() else []

                            gym_record = db.query(Gym).filter(Gym.id == inquiry.gym_id).first()
                            gym_name = gym_record.name if gym_record else 'Your gym'
                            subject, body = _build_inquiry_reminder_email(inquiry, inquiry.name, gym_name)
                            try:
                                sent = send_email(recipient, subject, body, is_html=True, cc_emails=cc_emails)
                                if not sent:
                                    continue
                                inquiry.last_reminded = date.today()
                                from app.models.inquiry import FollowUp
                                db.add(FollowUp(
                                    inquiry_id=inquiry.id,
                                    note='Automatic reminder email sent successfully',
                                    outcome='email_sent',
                                ))
                                db.add(inquiry)
                                db.commit()
                            except Exception:
                                db.rollback()
                    finally:
                        db.close()

                # schedule job to run every 5 minutes and decide send time from settings
                scheduler.add_job(followup_reminder_job, CronTrigger(minute='*/5'))
                scheduler.start()
                print('Follow-up reminder scheduler started (daily at 08:00 UTC)')
            except Exception as exc:
                print('Failed to start scheduler:', exc)
                print('If APScheduler is unavailable, install dependencies with: pip install -r requirements.txt')
                scheduler = None

    try:
        yield
    finally:
        try:
            if scheduler:
                scheduler.shutdown(wait=False)
        except Exception:
            pass
        if settings.db_backend == "mongo":
            close_mongodb()


app = FastAPI(title="Gym SaaS Platform | AI Attendance & Growth", lifespan=lifespan)


@app.middleware("http")
async def audit_api_mutations(request, call_next):
    response = await call_next(request)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code < 400:
        authorization = request.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            try:
                payload = decode_access_token(authorization[7:])
                actor_id = payload.get("sub")
                db = SessionLocal()
                actor = db.query(User).filter(User.id == actor_id).first()
                if actor and actor.gym_id and actor.role in (UserRole.STAFF, UserRole.TRAINER):
                    db.add(ActivityLog(
                        gym_id=actor.gym_id,
                        actor_id=actor.id,
                        action=f"api_{request.method.lower()}",
                        description=f"Completed {request.method} {request.url.path}",
                    ))
                    db.commit()
                db.close()
            except Exception:
                pass
    return response

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(members.router)
app.include_router(members.plans_router)
app.include_router(attendance.router)
app.include_router(payments.router)
app.include_router(dashboard.router)
app.include_router(churn.router)
app.include_router(classes.router)
app.include_router(notifications.router)
app.include_router(billing.router)
app.include_router(web.router)
app.include_router(support.router)


@app.get("/health")
def health_check():
    response = {"status": "ok", "db_backend": settings.db_backend}
    if settings.db_backend == "mongo":
        response["mongodb"] = mongo_health()
    return response
