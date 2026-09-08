"""Add optional payroll leave deduction override note.

Revision ID: 0005_payroll_override_note
Revises: 0004_payroll_leave_override
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_payroll_override_note"
down_revision = "0004_payroll_leave_override"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payroll_records", sa.Column("leave_deduction_override_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("payroll_records", "leave_deduction_override_note")