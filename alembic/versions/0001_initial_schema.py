"""Create the initial application schema.

Revision ID: 0001_initial_schema
Revises:
"""

from alembic import op

from app.core.database import Base
from app.models import activity_log, app_setting, attendance, gym, gym_class, inquiry
from app.models import member, payment, platform_plan, support, user, user_permission


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())