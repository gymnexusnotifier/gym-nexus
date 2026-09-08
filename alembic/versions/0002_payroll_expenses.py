"""Add payroll and expense tracking tables.

Revision ID: 0002_payroll_expenses
Revises: 0001_initial_schema
"""

from alembic import op
import sqlalchemy as sa

from app.models.enums import ExpenseCategory, PayFrequency, PayrollStatus
from app.models.gym import GUID


revision = "0002_payroll_expenses"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payroll_records",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("gym_id", GUID(), sa.ForeignKey("gyms.id"), nullable=False),
        sa.Column("staff_id", GUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("pay_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("pay_frequency", sa.Enum(PayFrequency, name="payfrequency"), nullable=False),
        sa.Column("pay_period_start", sa.Date(), nullable=False),
        sa.Column("pay_period_end", sa.Date(), nullable=False),
        sa.Column("days_in_period", sa.Numeric(8, 2), nullable=False),
        sa.Column("days_present", sa.Numeric(8, 2), nullable=False, server_default="0"),
        sa.Column("leave_days_unpaid", sa.Numeric(8, 2), nullable=False, server_default="0"),
        sa.Column("leave_deduction_amount", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("other_deductions", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("other_deductions_note", sa.Text(), nullable=True),
        sa.Column("gross_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("net_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", sa.Enum(PayrollStatus, name="payrollstatus"), nullable=False, server_default="PENDING"),
        sa.Column("released_date", sa.Date(), nullable=True),
        sa.Column("payslip_sent_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_payroll_records_gym_id", "payroll_records", ["gym_id"])
    op.create_index("ix_payroll_records_staff_id", "payroll_records", ["staff_id"])
    op.create_index("ix_payroll_records_deleted_at", "payroll_records", ["deleted_at"])
    op.create_table(
        "expenses",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("gym_id", GUID(), sa.ForeignKey("gyms.id"), nullable=False),
        sa.Column("category", sa.Enum(ExpenseCategory, name="expensecategory"), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("receipt_url", sa.Text(), nullable=True),
        sa.Column("created_by", GUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_expenses_gym_id", "expenses", ["gym_id"])
    op.create_index("ix_expenses_date", "expenses", ["date"])
    op.create_index("ix_expenses_deleted_at", "expenses", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("expenses")
    op.drop_table("payroll_records")