"""Explainable analytics used by the owner and platform dashboards."""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.attendance import Attendance
from app.models.expense import Expense
from app.models.gym_class import ClassBooking, GymClass
from app.models.inquiry import Inquiry, InquiryStatus
from app.models.member import Member, MemberStatus
from app.models.payment import Payment
from app.models.payroll import PayrollRecord
from app.models.enums import PayrollStatus
from app.models.user import User


def _hours_since(value: date | None, today: date) -> int | None:
    return (today - value).days if value else None


def build_gym_analytics(db: Session, gym_id, today: date | None = None) -> dict:
    today = today or date.today()
    active = db.query(Member).filter(
        Member.gym_id == gym_id, Member.status == MemberStatus.ACTIVE
    ).all()
    attendance = db.query(Attendance).filter(
        Attendance.gym_id == gym_id,
        Attendance.date >= today - timedelta(days=90),
    ).all()
    payments = db.query(Payment).filter(Payment.gym_id == gym_id).all()
    analytics = {
        "churn": _churn_insights(db, gym_id, active, attendance, payments, today),
        "revenue": _revenue_forecast(db, gym_id, active, payments, today),
        "traffic": _traffic_insights(attendance),
        "classes": _class_insights(db, gym_id, today),
        "inquiries": _inquiry_insights(db, gym_id, today),
        "expenses": _expense_insights(db, gym_id, len(active), today),
        "recommendations": _recommendations(db, gym_id, active, attendance),
        "anomalies": _anomaly_insights(db, gym_id, today),
    }
    return analytics


def _churn_insights(db, gym_id, members, attendance, payments, today):
    by_member = defaultdict(list)
    for row in attendance:
        by_member[row.member_id].append(row.date)
    latest_payment = {}
    for payment in payments:
        if payment.member_id not in latest_payment or payment.payment_date > latest_payment[payment.member_id].payment_date:
            latest_payment[payment.member_id] = payment

    results = []
    recent_start = today - timedelta(days=21)
    baseline_start = today - timedelta(days=42)
    for member in members:
        dates = by_member.get(member.id, [])
        recent = sum(recent_start <= value <= today for value in dates)
        baseline = sum(baseline_start <= value < recent_start for value in dates)
        last_visit = max(dates) if dates else None
        days_since_visit = _hours_since(last_visit, today)
        payment = latest_payment.get(member.id)
        days_since_payment = _hours_since(payment.payment_date, today) if payment else 999
        score = 0
        reasons = []
        if baseline >= 3 and recent == 0:
            score += 60
            reasons.append(f"was visiting {baseline / 3:.1f}x/week, now 0x in 3 weeks")
        elif baseline and recent < baseline * 0.5:
            score += 40
            reasons.append(f"attendance down {round((1 - recent / baseline) * 100)}% vs prior 3 weeks")
        elif days_since_visit is None or days_since_visit >= 10:
            score += 25
            reasons.append("no recent check-in")
        if days_since_payment >= 45:
            score += 25
            reasons.append(f"last payment {days_since_payment} days ago")
        elif payment and payment.next_due_date and payment.next_due_date < today:
            score += 15
            reasons.append("membership payment is overdue")
        score = min(score, 100)
        level = "high" if score >= 60 else "medium" if score >= 30 else "low"
        results.append({
            "id": str(member.id), "name": member.name, "score": score, "level": level,
            "recent_visits": recent, "baseline_visits": baseline,
            "reason": "; ".join(reasons) or "Stable attendance and payment pattern",
        })
    return sorted(results, key=lambda item: item["score"], reverse=True)


def _revenue_forecast(db, gym_id, members, payments, today):
    due = [p for p in payments if p.next_due_date and today <= p.next_due_date <= today + timedelta(days=30)]
    historical_due = [p for p in payments if p.next_due_date and today - timedelta(days=180) <= p.next_due_date < today]
    renewed = sum(1 for old in historical_due if any(
        later.member_id == old.member_id and old.next_due_date <= later.payment_date <= old.next_due_date + timedelta(days=30)
        for later in payments
    ))
    renewal_rate = round(renewed / len(historical_due) * 100, 1) if historical_due else 75.0
    expected = sum(float(p.amount or 0) for p in due) * renewal_rate / 100
    expiring = [{"name": p.member.name if p.member else "Member", "date": p.next_due_date, "amount": float(p.amount or 0)} for p in sorted(due, key=lambda item: item.next_due_date)]
    return {"expected": round(expected, 2), "renewal_rate": renewal_rate, "due_count": len(due), "expiring": expiring[:12]}


def _traffic_insights(attendance):
    hours = Counter()
    days = Counter()
    for row in attendance:
        try:
            hours[int(row.check_in_time.split(":")[0])] += 1
        except (AttributeError, ValueError):
            continue
        days[row.date.strftime("%a")] += 1
    max_hour = max(hours.values(), default=1)
    return {
        "hours": [{"label": f"{hour}:00", "value": count, "pct": round(count / max_hour * 100)} for hour, count in sorted(hours.items())],
        "days": [{"label": day, "value": days.get(day, 0)} for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")],
        "busiest_day": days.most_common(1)[0][0] if days else None,
        "busiest_hour": hours.most_common(1)[0][0] if hours else None,
    }


def _class_insights(db, gym_id, today):
    classes = db.query(GymClass).filter(GymClass.gym_id == gym_id).all()
    rows = []
    trainer_totals = defaultdict(lambda: {"bookings": 0, "retained": 0, "name": "Unassigned"})
    for gym_class in classes:
        bookings = db.query(ClassBooking).filter(ClassBooking.gym_id == gym_id, ClassBooking.class_id == gym_class.id).all()
        recent = sum(booking.booked_at.date() >= today - timedelta(days=30) for booking in bookings)
        prior = sum(today - timedelta(days=60) <= booking.booked_at.date() < today - timedelta(days=30) for booking in bookings)
        trend = "up" if recent > prior else "down" if recent < prior else "steady"
        rows.append({"name": gym_class.name, "attendance": len(bookings), "recent": recent, "trend": trend, "capacity": gym_class.capacity})
        trainer = trainer_totals[gym_class.trainer_id]
        trainer["bookings"] += len(bookings)
        trainer["retained"] += sum(booking.member and booking.member.status == MemberStatus.ACTIVE for booking in bookings)
        if gym_class.trainer:
            trainer["name"] = gym_class.trainer.email
    trainers = [{"name": item["name"], "retention": round(item["retained"] / item["bookings"] * 100, 1) if item["bookings"] else 0, "members": item["bookings"]} for item in trainer_totals.values()]
    return {"classes": sorted(rows, key=lambda item: item["attendance"], reverse=True)[:8], "trainers": sorted(trainers, key=lambda item: item["retention"], reverse=True)[:8]}


def _inquiry_insights(db, gym_id, today):
    inquiries = db.query(Inquiry).filter(Inquiry.gym_id == gym_id).all()
    converted = [item for item in inquiries if item.status == InquiryStatus.CONVERTED]
    cold = [item for item in inquiries if item.status not in (InquiryStatus.CONVERTED, InquiryStatus.LOST) and (today - item.created_at.date()).days >= 7 and (not item.next_followup or item.next_followup < today)]
    return {"total": len(inquiries), "converted": len(converted), "conversion_rate": round(len(converted) / len(inquiries) * 100, 1) if inquiries else 0, "cold": [{"name": item.name, "days": (today - item.created_at.date()).days} for item in cold[:10]]}


def _expense_insights(db, gym_id, active_member_count, today):
    start = today.replace(day=1)
    previous_start = (start - timedelta(days=1)).replace(day=1)
    current = defaultdict(float)
    previous = defaultdict(float)
    for item in db.query(Expense).filter(Expense.gym_id == gym_id, Expense.deleted_at.is_(None), Expense.date >= previous_start).all():
        target = current if item.date >= start else previous
        current_key = item.category.value if hasattr(item.category, "value") else str(item.category)
        target[current_key] += float(item.amount or 0)
    payroll = db.query(func.coalesce(func.sum(PayrollRecord.net_amount), 0)).filter(
        PayrollRecord.gym_id == gym_id,
        PayrollRecord.status == PayrollStatus.RELEASED,
        PayrollRecord.released_date >= start,
        PayrollRecord.deleted_at.is_(None),
    ).scalar() or 0
    total_cost = sum(current.values()) + float(payroll)
    categories = []
    for category, value in current.items():
        old = previous.get(category, 0)
        categories.append({"name": category.replace("_", " ").title(), "amount": round(value, 2), "growth": round((value - old) / old * 100, 1) if old else None})
    return {"cost_per_member": round(total_cost / active_member_count, 2) if active_member_count else 0, "categories": sorted(categories, key=lambda item: item["growth"] if item["growth"] is not None else 0, reverse=True)}


def _recommendations(db, gym_id, members, attendance):
    hour_counts = Counter()
    for row in attendance:
        try:
            hour_counts[int(row.check_in_time.split(":")[0])] += 1
        except (AttributeError, ValueError):
            pass
    suggestions = []
    peak = hour_counts.most_common(1)[0][0] if hour_counts else None
    for member in members[:10]:
        suggestions.append({"name": member.name, "suggestion": f"Try a coached class around {peak}:00" if peak is not None else "Explore a coached class this week"})
    return suggestions


def _anomaly_insights(db, gym_id, today):
    this_start = today.replace(day=1)
    previous_start = (this_start - timedelta(days=1)).replace(day=1)
    this_payments = db.query(Payment).filter(Payment.gym_id == gym_id, Payment.payment_date >= this_start).count()
    previous_payments = db.query(Payment).filter(Payment.gym_id == gym_id, Payment.payment_date >= previous_start, Payment.payment_date < this_start).count()
    anomalies = []
    odd_hour_count = 0
    for row in db.query(Attendance).filter(Attendance.gym_id == gym_id, Attendance.date >= today - timedelta(days=30)).all():
        try:
            hour = int(row.check_in_time.split(":")[0])
            odd_hour_count += hour < 5 or hour >= 23
        except (AttributeError, ValueError):
            continue
    if odd_hour_count:
        anomalies.append(f"{odd_hour_count} attendance record(s) were logged before 05:00 or after 23:00")
    if previous_payments >= 3 and this_payments < previous_payments * 0.5:
        anomalies.append(f"Payment volume is down {round((1 - this_payments / previous_payments) * 100)}% month over month")
    return anomalies
