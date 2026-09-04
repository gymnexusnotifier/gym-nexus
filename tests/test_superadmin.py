from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models.enums import UserRole
from app.models.user import User

TEST_DB_URL = "sqlite:///./test_superadmin.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def _login_as_superadmin(email: str = "superadmin@test.com", password: str = "SuperAdmin@123"):
    db = TestingSessionLocal()
    existing = db.query(User).filter(User.email == email).first()
    if existing is None:
        db.add(User(email=email, hashed_password=hash_password(password), role=UserRole.SUPER_ADMIN))
        db.commit()
    db.close()
    response = client.post("/login", data={"email": email, "password": password}, follow_redirects=False)
    assert response.status_code == 303
    return response


def test_superadmin_can_manage_platform_plans_and_gyms():
    _login_as_superadmin()

    plan_create = client.post(
        "/app/superadmin/platform-plans",
        data={"name": "Pro Plus", "price": "2999", "billing_interval": "monthly", "member_limit": "100", "razorpay_plan_id": "plan_123"},
        follow_redirects=False,
    )
    assert plan_create.status_code == 303

    db = TestingSessionLocal()
    from app.models.platform_plan import PlatformPlan
    plan = db.query(PlatformPlan).filter(PlatformPlan.name == "Pro Plus").first()
    assert plan is not None
    plan_id = str(plan.id)
    db.close()

    plan_update = client.post(
        f"/app/superadmin/platform-plans/{plan_id}/update",
        data={"name": "Pro Plus Updated", "price": "3499", "billing_interval": "quarterly", "member_limit": "120", "razorpay_plan_id": "plan_456"},
        follow_redirects=False,
    )
    assert plan_update.status_code == 303

    gym_create = client.post(
        "/app/superadmin/gyms",
        data={"name": "Alpha Gym", "owner_email": "owner@alpha.com", "owner_password": "OwnerPass!123", "platform_plan_id": plan_id, "subscription_status": "trial"},
        follow_redirects=False,
    )
    assert gym_create.status_code == 303

    db = TestingSessionLocal()
    from app.models.gym import Gym
    gym = db.query(Gym).filter(Gym.name == "Alpha Gym").first()
    assert gym is not None
    gym_id = str(gym.id)
    owner = db.query(User).filter(User.gym_id == gym.id, User.role == UserRole.GYM_OWNER).first()
    assert owner is not None
    assert owner.email == "owner@alpha.com"
    db.close()

    gym_update = client.post(
        f"/app/superadmin/gyms/{gym_id}/update",
        data={"name": "Alpha Gym Updated", "owner_email": "newowner@alpha.com", "owner_password": "NewOwnerPass!123", "platform_plan_id": plan_id, "subscription_status": "active"},
        follow_redirects=False,
    )
    assert gym_update.status_code == 303

    db = TestingSessionLocal()
    updated_owner = db.query(User).filter(User.gym_id == gym.id, User.role == UserRole.GYM_OWNER).first()
    assert updated_owner.email == "newowner@alpha.com"
    db.close()

    gym_delete = client.post(f"/app/superadmin/gyms/{gym_id}/delete", follow_redirects=False)
    assert gym_delete.status_code == 303

    plan_delete = client.post(f"/app/superadmin/platform-plans/{plan_id}/delete", follow_redirects=False)
    assert plan_delete.status_code == 303
