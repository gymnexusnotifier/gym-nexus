"""
One-time CLI script to create your first super_admin login.
Not exposed via HTTP on purpose.

Usage:
    python -m scripts.create_superadmin you@example.com yourpassword
"""
import sys

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User
from app.models.enums import UserRole


def create_superadmin(email: str, password: str):
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print(f"User {email} already exists.")
            return
        user = User(
            gym_id=None,
            email=email,
            hashed_password=hash_password(password),
            role=UserRole.SUPER_ADMIN,
        )
        db.add(user)
        db.commit()
        print(f"Super admin created: {email}")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python -m scripts.create_superadmin <email> <password>")
        sys.exit(1)
    create_superadmin(sys.argv[1], sys.argv[2])
