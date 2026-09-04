from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db
from app.models.platform_plan import PlatformPlan

TEST_DB_URL = "sqlite:///./test_billing.db"
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


def _seed_plan():
    db = TestingSessionLocal()
    plan = PlatformPlan(name="Basic", price="999.00", billing_interval="monthly", member_limit=100)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    plan_id = str(plan.id)
    db.close()
    return plan_id


def _signup(gym_name, email, password):
    resp = client.post("/auth/signup", json={
        "gym_name": gym_name,
        "owner_email": email,
        "owner_password": password,
    })
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_signup_starts_trial_and_subscribe_activates_plan():
    token = _signup("Gym Upsilon", "upsilon_owner@example.com", "password123")

    plans_resp = client.get("/billing/plans")
    assert plans_resp.status_code == 200

    status_resp = client.get("/billing/status", headers=_auth_headers(token))
    assert status_resp.status_code == 200
    initial = status_resp.json()
    assert initial["subscription_status"] == "trial"
    assert initial["trial_ends_at"] is not None

    plan_id = _seed_plan()

    subscribe_resp = client.post(
        "/billing/subscribe",
        json={"platform_plan_id": plan_id},
        headers=_auth_headers(token),
    )
    assert subscribe_resp.status_code == 200
    sub_data = subscribe_resp.json()
    assert sub_data["status"] == "active"
    assert sub_data["razorpay_subscription_id"].startswith("sim_sub_")

    status_after = client.get("/billing/status", headers=_auth_headers(token))
    assert status_after.status_code == 200
    after_data = status_after.json()
    assert after_data["subscription_status"] == "active"
    assert after_data["plan_name"] == "Basic"
