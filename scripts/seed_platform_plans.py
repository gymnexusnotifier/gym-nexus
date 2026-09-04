"""
One-time seed script for YOUR platform's subscription tiers
(what gyms pay you - separate from a gym's own member pricing).

Usage:
    python -m scripts.seed_platform_plans
"""
from app.core.database import SessionLocal
from app.models.platform_plan import PlatformPlan

PLANS = [
    {"name": "Basic", "price": "999.00", "billing_interval": "monthly", "member_limit": 100},
    {"name": "Pro", "price": "2499.00", "billing_interval": "monthly", "member_limit": None},
    {"name": "Enterprise", "price": "4999.00", "billing_interval": "monthly", "member_limit": None},
]


def seed():
    db = SessionLocal()
    try:
        for plan_data in PLANS:
            existing = db.query(PlatformPlan).filter(PlatformPlan.name == plan_data["name"]).first()
            if existing:
                print(f"Plan '{plan_data['name']}' already exists, skipping.")
                continue
            db.add(PlatformPlan(**plan_data))
            print(f"Created plan: {plan_data['name']}")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
