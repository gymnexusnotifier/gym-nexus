"""Add recurring salary settings to staff users.

Revision ID: 0006_staff_salary_settings
Revises: 0005_payroll_override_note
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.models.enums import PayFrequency


revision = "0006_staff_salary_settings"
down_revision = "0005_payroll_override_note"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("salary_rate", sa.Numeric(10, 2), nullable=True))
    op.add_column("users", sa.Column("salary_frequency", postgresql.ENUM(PayFrequency, name="payfrequency", create_type=False), nullable=True))
    op.add_column("users", sa.Column("salary_start_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "salary_start_date")
    op.drop_column("users", "salary_frequency")
    op.drop_column("users", "salary_rate")