import enum


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    GYM_OWNER = "gym_owner"
    STAFF = "staff"
    TRAINER = "trainer"


class PayFrequency(str, enum.Enum):
    MONTHLY = "monthly"
    WEEKLY = "weekly"
    PER_SESSION = "per-session"


class PayrollStatus(str, enum.Enum):
    PENDING = "pending"
    RELEASED = "released"


class ExpenseCategory(str, enum.Enum):
    RENT = "rent"
    UTILITIES = "utilities"
    EQUIPMENT = "equipment"
    MAINTENANCE = "maintenance"
    MARKETING = "marketing"
    OTHER = "other"


class LeaveType(str, enum.Enum):
    PAID = "paid"
    UNPAID = "unpaid"
