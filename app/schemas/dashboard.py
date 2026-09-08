from decimal import Decimal

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    today_checkins: int
    currently_in_gym: int
    active_members: int
    expired_members: int
    frozen_members: int
    monthly_revenue: Decimal
    total_expenses_this_month: Decimal = Decimal("0")


class PeakHourEntry(BaseModel):
    hour: int
    checkins: int
