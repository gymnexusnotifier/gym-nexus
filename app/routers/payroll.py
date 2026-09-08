import calendar
import uuid
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_gym_id, require_role
from app.core.email import build_payslip_email, send_email
from app.models.enums import PayrollStatus, UserRole
from app.models.expense import Expense
from app.models.gym import Gym
from app.models.member import Member
from app.models.payment import Payment
from app.models.payroll import PayrollRecord
from app.models.user import User
from app.routers.leave import count_unpaid_leave_days
from app.schemas.payroll import (
    ExpenseCreate, ExpenseResponse, ExpenseSummary, ExpenseUpdate,
    MonthlyExpenseSummary, PayrollCreate, PayrollResponse, PayrollUpdate,
)
from app.services.receipt import generate_expense_summary_pdf, generate_payslip_pdf

router = APIRouter(prefix="/payroll", tags=["payroll"])
MONEY = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def _log(db: Session, user: User, action: str, description: str):
    from app.models.activity_log import ActivityLog
    db.add(ActivityLog(gym_id=user.gym_id, actor_id=user.id, action=action, description=description))


def _staff_or_404(db: Session, staff_id: uuid.UUID, gym_id: uuid.UUID) -> User:
    staff = db.query(User).filter(
        User.id == staff_id,
        User.gym_id == gym_id,
        User.role.in_([UserRole.STAFF, UserRole.TRAINER]),
    ).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")
    return staff


def _payroll_or_404(db: Session, payroll_id: uuid.UUID, gym_id: uuid.UUID) -> PayrollRecord:
    record = db.query(PayrollRecord).filter(
        PayrollRecord.id == payroll_id,
        PayrollRecord.gym_id == gym_id,
        PayrollRecord.deleted_at.is_(None),
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Payroll record not found")
    return record


def _expense_or_404(db: Session, expense_id: uuid.UUID, gym_id: uuid.UUID) -> Expense:
    expense = db.query(Expense).filter(
        Expense.id == expense_id,
        Expense.gym_id == gym_id,
        Expense.deleted_at.is_(None),
    ).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    return expense


def _deduction(payload: PayrollCreate | PayrollUpdate, pay_rate: Decimal, days_in_period: Decimal) -> Decimal:
    if payload.leave_deduction_amount is not None:
        return _money(payload.leave_deduction_amount)
    return _money(pay_rate / days_in_period * payload.leave_days_unpaid)


def _auto_leave_days(db: Session, gym_id: uuid.UUID, staff_id: uuid.UUID, start: date, end: date) -> Decimal:
    return count_unpaid_leave_days(db, gym_id, staff_id, start, end)


@router.get("/leave-preview")
def leave_preview(
    staff_id: uuid.UUID,
    pay_period_start: date,
    pay_period_end: date,
    pay_rate: Decimal,
    days_in_period: Decimal,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_role("gym_owner")),
):
    _staff_or_404(db, staff_id, gym_id)
    if pay_rate <= 0 or days_in_period <= 0 or pay_period_end < pay_period_start:
        raise HTTPException(status_code=400, detail="Invalid salary period or rate")
    leave_days = _auto_leave_days(db, gym_id, staff_id, pay_period_start, pay_period_end)
    deduction = _money(pay_rate / days_in_period * leave_days)
    return {"unpaid_leave_days": leave_days, "per_day_rate": _money(pay_rate / days_in_period), "leave_deduction_amount": deduction, "net_amount": _money(pay_rate - deduction)}


@router.post("", response_model=PayrollResponse)
def create_payroll(
    payload: PayrollCreate,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    user: User = Depends(require_role("gym_owner")),
):
    _staff_or_404(db, payload.staff_id, gym_id)
    overlap = db.query(PayrollRecord).filter(
        PayrollRecord.gym_id == gym_id,
        PayrollRecord.staff_id == payload.staff_id,
        PayrollRecord.deleted_at.is_(None),
        PayrollRecord.pay_period_start <= payload.pay_period_end,
        PayrollRecord.pay_period_end >= payload.pay_period_start,
    ).first()
    if overlap:
        raise HTTPException(status_code=409, detail="A payroll record already exists for an overlapping period")

    leave_days = _auto_leave_days(db, gym_id, payload.staff_id, payload.pay_period_start, payload.pay_period_end)
    deduction = _money(payload.leave_deduction_amount) if payload.leave_deduction_amount is not None else _money(payload.pay_rate / payload.days_in_period * leave_days)
    net = _money(payload.pay_rate - deduction - payload.other_deductions)
    if net < 0:
        raise HTTPException(status_code=400, detail="Deductions cannot exceed gross amount")
    record = PayrollRecord(
        gym_id=gym_id, staff_id=payload.staff_id, pay_rate=payload.pay_rate,
        pay_frequency=payload.pay_frequency, pay_period_start=payload.pay_period_start,
        pay_period_end=payload.pay_period_end, days_in_period=payload.days_in_period,
        days_present=payload.days_present, leave_days_unpaid=leave_days,
        leave_deduction_amount=deduction, other_deductions=payload.other_deductions,
        leave_deduction_overridden=payload.leave_deduction_amount is not None,
        leave_deduction_override_note=payload.leave_deduction_override_note,
        other_deductions_note=payload.other_deductions_note, gross_amount=payload.pay_rate,
        net_amount=net,
    )
    db.add(record)
    _log(db, user, "payroll_created", f"Created payroll record for staff {payload.staff_id}: Rs. {net}")
    db.commit()
    db.refresh(record)
    return record


@router.get("", response_model=List[PayrollResponse])
def list_payroll(
    staff_id: Optional[uuid.UUID] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_role("gym_owner")),
):
    query = db.query(PayrollRecord).filter(PayrollRecord.gym_id == gym_id, PayrollRecord.deleted_at.is_(None))
    if staff_id:
        query = query.filter(PayrollRecord.staff_id == staff_id)
    if start_date:
        query = query.filter(PayrollRecord.pay_period_end >= start_date)
    if end_date:
        query = query.filter(PayrollRecord.pay_period_start <= end_date)
    return query.order_by(PayrollRecord.pay_period_start.desc()).all()


@router.patch("/{payroll_id}", response_model=PayrollResponse)
def update_payroll(
    payroll_id: uuid.UUID,
    payload: PayrollUpdate,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    user: User = Depends(require_role("gym_owner")),
):
    record = _payroll_or_404(db, payroll_id, gym_id)
    if record.status == PayrollStatus.RELEASED:
        raise HTTPException(status_code=400, detail="Released payroll records cannot be edited")
    values = payload.model_dump(exclude_unset=True)
    for key, value in values.items():
        if value is not None:
            setattr(record, key, value)
    record.leave_days_unpaid = _auto_leave_days(db, gym_id, record.staff_id, record.pay_period_start, record.pay_period_end)
    if values.get("leave_deduction_amount") is not None:
        record.leave_deduction_amount = values["leave_deduction_amount"]
        record.leave_deduction_overridden = True
    else:
        record.leave_deduction_amount = _money(record.pay_rate / record.days_in_period * record.leave_days_unpaid)
    record.net_amount = _money(record.gross_amount - record.leave_deduction_amount - record.other_deductions)
    if record.net_amount < 0:
        raise HTTPException(status_code=400, detail="Deductions cannot exceed gross amount")
    _log(db, user, "payroll_updated", f"Updated payroll record {payroll_id}")
    db.commit()
    db.refresh(record)
    return record


@router.delete("/{payroll_id}", status_code=204)
def delete_payroll(
    payroll_id: uuid.UUID,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    user: User = Depends(require_role("gym_owner")),
):
    record = _payroll_or_404(db, payroll_id, gym_id)
    record.deleted_at = datetime.utcnow()
    _log(db, user, "payroll_deleted", f"Soft-deleted payroll record {payroll_id}")
    db.commit()


def _send_payslip(record: PayrollRecord, staff: User, gym: Gym, db: Session) -> bool:
    subject, body = build_payslip_email(gym.name if gym else "Your gym", staff.email, record)
    pdf = generate_payslip_pdf(gym.name if gym else "Gym", staff.email, record)
    sent = send_email(staff.email, subject, body, is_html=True, attachments=[
        (f"payslip_{str(record.id)[:8]}.pdf", pdf.read(), "application/pdf")
    ])
    if sent:
        record.payslip_sent_at = datetime.utcnow()
        db.commit()
    return sent


@router.post("/{payroll_id}/release", response_model=PayrollResponse)
def release_payroll(
    payroll_id: uuid.UUID,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    user: User = Depends(require_role("gym_owner")),
):
    record = _payroll_or_404(db, payroll_id, gym_id)
    staff = _staff_or_404(db, record.staff_id, gym_id)
    if record.status == PayrollStatus.PENDING:
        if not record.leave_deduction_overridden:
            record.leave_days_unpaid = _auto_leave_days(db, gym_id, record.staff_id, record.pay_period_start, record.pay_period_end)
            record.leave_deduction_amount = _money(record.pay_rate / record.days_in_period * record.leave_days_unpaid)
            record.net_amount = _money(record.gross_amount - record.leave_deduction_amount - record.other_deductions)
        record.status = PayrollStatus.RELEASED
        record.released_date = date.today()
        _log(db, user, "payroll_released", f"Released Rs. {record.net_amount} to {staff.email}")
        db.commit()
    gym = db.query(Gym).filter(Gym.id == gym_id).first()
    _send_payslip(record, staff, gym, db)
    db.refresh(record)
    return record


@router.post("/{payroll_id}/resend-payslip", response_model=PayrollResponse)
def resend_payslip(
    payroll_id: uuid.UUID,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_role("gym_owner")),
):
    record = _payroll_or_404(db, payroll_id, gym_id)
    if record.status != PayrollStatus.RELEASED:
        raise HTTPException(status_code=400, detail="Only released payroll records have payslips")
    staff = _staff_or_404(db, record.staff_id, gym_id)
    gym = db.query(Gym).filter(Gym.id == gym_id).first()
    _send_payslip(record, staff, gym, db)
    db.refresh(record)
    return record


@router.get("/{payroll_id}/payslip")
def download_payslip(
    payroll_id: uuid.UUID,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_role("gym_owner")),
):
    record = _payroll_or_404(db, payroll_id, gym_id)
    staff = _staff_or_404(db, record.staff_id, gym_id)
    gym = db.query(Gym).filter(Gym.id == gym_id).first()
    return StreamingResponse(
        generate_payslip_pdf(gym.name if gym else "Gym", staff.email, record),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=payslip_{str(record.id)[:8]}.pdf"},
    )


@router.post("/expenses", response_model=ExpenseResponse)
def create_expense(
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    user: User = Depends(require_role("gym_owner")),
):
    expense = Expense(gym_id=gym_id, created_by=user.id, **payload.model_dump())
    db.add(expense)
    _log(db, user, "expense_created", f"Recorded {payload.category.value} expense: Rs. {payload.amount}")
    db.commit()
    db.refresh(expense)
    return expense


@router.get("/expenses", response_model=List[ExpenseResponse])
def list_expenses(
    category: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_role("gym_owner")),
):
    query = db.query(Expense).filter(Expense.gym_id == gym_id, Expense.deleted_at.is_(None))
    if category:
        query = query.filter(Expense.category == category)
    if start_date:
        query = query.filter(Expense.date >= start_date)
    if end_date:
        query = query.filter(Expense.date <= end_date)
    return query.order_by(Expense.date.desc()).all()


@router.patch("/expenses/{expense_id}", response_model=ExpenseResponse)
def update_expense(
    expense_id: uuid.UUID,
    payload: ExpenseUpdate,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    user: User = Depends(require_role("gym_owner")),
):
    expense = _expense_or_404(db, expense_id, gym_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(expense, key, value)
    _log(db, user, "expense_updated", f"Updated expense {expense_id}")
    db.commit()
    db.refresh(expense)
    return expense


@router.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(
    expense_id: uuid.UUID,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    user: User = Depends(require_role("gym_owner")),
):
    expense = _expense_or_404(db, expense_id, gym_id)
    expense.deleted_at = datetime.utcnow()
    _log(db, user, "expense_deleted", f"Soft-deleted expense {expense_id}")
    db.commit()


@router.get("/summary", response_model=ExpenseSummary)
def expense_summary(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_role("gym_owner")),
):
    start_date = start_date or date.today().replace(day=1)
    end_date = end_date or date.today()
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")
    payroll_rows = db.query(PayrollRecord).filter(
        PayrollRecord.gym_id == gym_id, PayrollRecord.status == PayrollStatus.RELEASED,
        PayrollRecord.deleted_at.is_(None), PayrollRecord.released_date >= start_date,
        PayrollRecord.released_date <= end_date,
    ).all()
    expense_rows = db.query(Expense).filter(
        Expense.gym_id == gym_id, Expense.deleted_at.is_(None),
        Expense.date >= start_date, Expense.date <= end_date,
    ).all()
    income = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.gym_id == gym_id, Payment.payment_date >= start_date, Payment.payment_date <= end_date,
    ).scalar() or 0
    payroll_total = _money(sum((row.net_amount for row in payroll_rows), Decimal("0")))
    expense_total = _money(sum((row.amount for row in expense_rows), Decimal("0")))
    by_month = defaultdict(lambda: [Decimal("0"), Decimal("0")])
    for row in payroll_rows:
        by_month[row.released_date.strftime("%Y-%m")][0] += row.net_amount
    for row in expense_rows:
        by_month[row.date.strftime("%Y-%m")][1] += row.amount
    months = []
    cursor = start_date.replace(day=1)
    while cursor <= end_date:
        key = cursor.strftime("%Y-%m")
        payroll, other = by_month[key]
        months.append(MonthlyExpenseSummary(month=key, payroll=_money(payroll), other_expenses=_money(other), total=_money(payroll + other)))
        cursor = date(cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1, 1)
    total = _money(payroll_total + expense_total)
    income = _money(Decimal(str(income)))
    return ExpenseSummary(
        total_payroll=payroll_total, total_other_expenses=expense_total,
        combined_total=total, total_income=income, net_profit=_money(income - total), by_month=months,
    )


@router.get("/summary/pdf")
def download_expense_summary_pdf(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    gym_id: uuid.UUID = Depends(get_current_gym_id),
    _=Depends(require_role("gym_owner")),
):
    summary = expense_summary(start_date, end_date, db, gym_id, _)
    return StreamingResponse(
        generate_expense_summary_pdf("Gym", start_date or date.today().replace(day=1), end_date or date.today(), summary.total_payroll, summary.total_other_expenses, summary.total_income, summary.by_month),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=payroll_expense_summary.pdf"},
    )