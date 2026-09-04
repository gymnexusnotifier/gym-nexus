"""Seed repeatable demo data for the AFC gym."""

import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.attendance import Attendance
from app.models.enums import UserRole
from app.models.gym import Gym
from app.models.gym_class import ClassBooking, GymClass
from app.models.inquiry import FollowUp, Inquiry, InquiryStatus
from app.models.member import Member, MemberStatus, MembershipPlan
from app.models.payment import Payment
from app.models.user import User
from app.models.activity_log import ActivityLog

DEMO_PREFIX = "demo.afc."


def main() -> None:
    db = SessionLocal()
    try:
        gym = db.query(Gym).filter(Gym.name.ilike("AFC")).first()
        if not gym:
            raise SystemExit("AFC gym was not found")

        existing = db.query(User).filter(User.email.like(f"{DEMO_PREFIX}%")).count()
        if existing:
            print("AFC demo data already exists; nothing changed.")
            return

        plans = db.query(MembershipPlan).filter(MembershipPlan.gym_id == gym.id).order_by(MembershipPlan.price).all()
        if len(plans) < 2:
            plans = [
                MembershipPlan(gym_id=gym.id, name="Demo Monthly", price=2000, duration_days=30),
                MembershipPlan(gym_id=gym.id, name="Demo Premium", price=5000, duration_days=90),
            ]
            db.add_all(plans)
            db.flush()

        staff = User(gym_id=gym.id, email=f"{DEMO_PREFIX}staff@example.com", hashed_password=hash_password("DemoStaff!123"), role=UserRole.STAFF)
        trainer = User(gym_id=gym.id, email=f"{DEMO_PREFIX}trainer@example.com", hashed_password=hash_password("DemoTrainer!123"), role=UserRole.TRAINER)
        db.add_all([staff, trainer])
        db.flush()

        member_specs = [
            ("Demo Active Regular", "active", plans[0], "active1@example.com"),
            ("Demo Active Premium", "active", plans[-1], "active2@example.com"),
            ("Demo Expired Member", "expired", plans[0], "expired@example.com"),
            ("Demo Frozen Member", "frozen", plans[0], "frozen@example.com"),
            ("Demo No Email", "active", None, None),
        ]
        members = []
        for index, (name, status, plan, email) in enumerate(member_specs):
            member = Member(
                gym_id=gym.id,
                name=name,
                contact=f"90000000{index + 1:02d}",
                email=email,
                plan_id=plan.id if plan else None,
                status=MemberStatus(status),
                join_date=date.today() - timedelta(days=30 + index * 20),
            )
            db.add(member)
            members.append(member)
        db.flush()

        today = date.today()
        attendance_specs = [
            (members[0], today, "07:15:00", "08:20:00"),
            (members[1], today, "18:10:00", None),
            (members[0], today - timedelta(days=1), "18:30:00", "19:35:00"),
            (members[1], today - timedelta(days=2), "12:00:00", "12:45:00"),
            (members[2], today - timedelta(days=4), "06:45:00", "07:30:00"),
            (members[3], today - timedelta(days=8), "14:00:00", "14:40:00"),
            (members[0], today - timedelta(days=12), "18:00:00", "19:00:00"),
            (members[1], today - timedelta(days=15), "18:15:00", "19:15:00"),
            (members[0], today - timedelta(days=20), "07:30:00", "08:30:00"),
            (members[1], today - timedelta(days=25), "21:00:00", "21:45:00"),
        ]
        for member, visit_date, check_in, check_out in attendance_specs:
            db.add(Attendance(gym_id=gym.id, member_id=member.id, date=visit_date, check_in_time=check_in, check_out_time=check_out, status="present"))

        payment_specs = [
            (members[0], plans[0], "2000.00", "cash", None, today),
            (members[1], plans[-1], "5000.00", "upi", "DEMO-UPI-20260904-001", today),
            (members[2], plans[0], "2000.00", "card", "DEMO-CARD-001", today - timedelta(days=40)),
            (members[3], plans[0], "2000.00", "bank_transfer", "DEMO-BANK-001", today - timedelta(days=10)),
        ]
        for member, plan, amount, method, transaction_id, paid_on in payment_specs:
            db.add(Payment(gym_id=gym.id, member_id=member.id, plan_id=plan.id, amount=Decimal(amount), payment_date=paid_on, next_due_date=paid_on + timedelta(days=plan.duration_days), payment_method=method, transaction_id=transaction_id))

        classes = [
            GymClass(gym_id=gym.id, trainer_id=trainer.id, name="Demo Morning Strength", day_of_week=0, start_time="07:00", duration_minutes=60, capacity=12),
            GymClass(gym_id=gym.id, trainer_id=trainer.id, name="Demo Evening HIIT", day_of_week=2, start_time="18:30", duration_minutes=45, capacity=8),
        ]
        db.add_all(classes)
        db.flush()
        db.add_all([
            ClassBooking(gym_id=gym.id, class_id=classes[0].id, member_id=members[0].id),
            ClassBooking(gym_id=gym.id, class_id=classes[1].id, member_id=members[1].id),
        ])

        inquiry_specs = [
            ("Demo New Lead", InquiryStatus.NEW, None),
            ("Demo Scheduled Lead", InquiryStatus.SCHEDULED, today),
            ("Demo Converted Lead", InquiryStatus.CONVERTED, today - timedelta(days=3)),
            ("Demo Lost Lead", InquiryStatus.LOST, today - timedelta(days=5)),
        ]
        for name, status, followup_date in inquiry_specs:
            inquiry = Inquiry(gym_id=gym.id, name=name, contact="9111111111", email=f"{name.lower().replace(' ', '.')}@example.com", source="demo", status=status, next_followup=followup_date, assigned_staff_id=staff.id)
            db.add(inquiry)
            db.flush()
            if followup_date:
                db.add(FollowUp(inquiry_id=inquiry.id, staff_id=staff.id, note="Demo follow-up history entry", outcome="scheduled"))

        db.add_all([
            ActivityLog(gym_id=gym.id, actor_id=staff.id, action="member_created", description="Added member Demo Active Regular"),
            ActivityLog(gym_id=gym.id, actor_id=staff.id, action="payment_recorded", description="Recorded UPI payment for Demo Active Premium: Rs. 5000.00"),
            ActivityLog(gym_id=gym.id, actor_id=trainer.id, action="class_booked", description="Booked Demo Active Premium into Demo Evening HIIT"),
            ActivityLog(gym_id=gym.id, actor_id=staff.id, action="inquiry_reminder_sent", description="Sent reminder for Demo Scheduled Lead"),
        ])
        db.commit()
        print("Seeded AFC demo data. Demo credentials: demo.afc.staff@example.com / DemoStaff!123 and demo.afc.trainer@example.com / DemoTrainer!123")
    finally:
        db.close()


if __name__ == "__main__":
    main()
