import enum


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    GYM_OWNER = "gym_owner"
    STAFF = "staff"
    TRAINER = "trainer"
