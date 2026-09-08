import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ExpenseCategory, PayFrequency, PayrollStatus


class PayrollCreate(BaseModel):
    staff_id: uuid.UUID
    pay_rate: Decimal = Field(gt=0)
    pay_frequency: PayFrequency
    pay_period_start: date
    pay_period_end: date
    days_in_period: Decimal = Field(gt=0)
    days_present: Decimal = Field(default=Decimal("0"), ge=0)
    leave_deduction_amount: Optional[Decimal] = Field(default=None, ge=0)
    leave_deduction_override_note: Optional[str] = None
    other_deductions: Decimal = Field(default=Decimal("0"), ge=0)
    other_deductions_note: Optional[str] = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.pay_period_end < self.pay_period_start:
            raise ValueError("pay_period_end must be on or after pay_period_start")
        return self


class PayrollUpdate(BaseModel):
    days_present: Optional[Decimal] = Field(default=None, ge=0)
    leave_deduction_amount: Optional[Decimal] = Field(default=None, ge=0)
    leave_deduction_override_note: Optional[str] = None
    other_deductions: Optional[Decimal] = Field(default=None, ge=0)
    other_deductions_note: Optional[str] = None


class PayrollResponse(BaseModel):
    id: uuid.UUID
    staff_id: uuid.UUID
    pay_rate: Decimal
    pay_frequency: PayFrequency
    pay_period_start: date
    pay_period_end: date
    days_in_period: Decimal
    days_present: Decimal
    leave_days_unpaid: Decimal
    leave_deduction_amount: Decimal
    other_deductions: Decimal
    other_deductions_note: Optional[str]
    gross_amount: Decimal
    net_amount: Decimal
    status: PayrollStatus
    released_date: Optional[date]
    payslip_sent_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class ExpenseCreate(BaseModel):
    category: ExpenseCategory
    amount: Decimal = Field(gt=0)
    date: date
    description: str = Field(min_length=1, max_length=2000)
    receipt_url: Optional[str] = None


class ExpenseUpdate(BaseModel):
    category: Optional[ExpenseCategory] = None
    amount: Optional[Decimal] = Field(default=None, gt=0)
    date: Optional[date] = None
    description: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    receipt_url: Optional[str] = None


class ExpenseResponse(BaseModel):
    id: uuid.UUID
    category: ExpenseCategory
    amount: Decimal
    date: date
    description: str
    receipt_url: Optional[str]
    created_by: uuid.UUID

    model_config = ConfigDict(from_attributes=True)


class MonthlyExpenseSummary(BaseModel):
    month: str
    payroll: Decimal
    other_expenses: Decimal
    total: Decimal


class ExpenseSummary(BaseModel):
    total_payroll: Decimal
    total_other_expenses: Decimal
    combined_total: Decimal
    total_income: Decimal
    net_profit: Decimal
    by_month: list[MonthlyExpenseSummary]