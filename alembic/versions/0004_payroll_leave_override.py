"""Track manual payroll leave deduction overrides.

Revision ID: 0004_payroll_leave_override
Revises: 0003_staff_leave
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_payroll_leave_override"
down_revision = "0003_staff_leave"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payroll_records", sa.Column("leave_deduction_overridden", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("payroll_records", "leave_deduction_overridden")