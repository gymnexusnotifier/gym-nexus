"""Add staff leave tracking records.

Revision ID: 0003_staff_leave
Revises: 0002_payroll_expenses
"""

from alembic import op
import sqlalchemy as sa

from app.models.enums import LeaveType
from app.models.gym import GUID


revision = "0003_staff_leave"
down_revision = "0002_payroll_expenses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_leaves",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("gym_id", GUID(), sa.ForeignKey("gyms.id"), nullable=False),
        sa.Column("staff_id", GUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("leave_type", sa.Enum(LeaveType, name="leavetype"), nullable=False, server_default="UNPAID"),
        sa.Column("day_fraction", sa.Numeric(3, 2), nullable=False, server_default="1"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_staff_leaves_gym_id", "staff_leaves", ["gym_id"])
    op.create_index("ix_staff_leaves_staff_id", "staff_leaves", ["staff_id"])
    op.create_index("ix_staff_leaves_start_date", "staff_leaves", ["start_date"])
    op.create_index("ix_staff_leaves_end_date", "staff_leaves", ["end_date"])
    op.create_index("ix_staff_leaves_deleted_at", "staff_leaves", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("staff_leaves")