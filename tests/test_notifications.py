from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db
from app.models.member import Member

TEST_DB_URL = "sqlite:///./test_notifications.db"
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


def _set_join_date(member_id: str, days_ago: int):
    db = TestingSessionLocal()
    member = db.query(Member).filter(Member.id == member_id).first()
    member.join_date = date.today() - timedelta(days=days_ago)
    db.commit()
    db.close()


def test_renewal_reminder_sends_only_to_members_with_email():
    token = _signup("Gym Sigma", "sigma_owner@example.com", "password123")

    plan_resp = client.post(
        "/plans",
        json={"name": "Weekly", "price": "500.00", "duration_days": 5},
        headers=_auth_headers(token),
    )
    plan_id = plan_resp.json()["id"]

    member_with_email = client.post(
        "/members",
        json={"name": "Has Email", "email": "hasmail@example.com"},
        headers=_auth_headers(token),
    ).json()

    member_without_email = client.post(
        "/members",
        json={"name": "No Email"},
        headers=_auth_headers(token),
    ).json()

    for member in (member_with_email, member_without_email):
        client.post(
            "/payments",
            json={"member_id": member["id"], "plan_id": plan_id, "amount": "500.00"},
            headers=_auth_headers(token),
        )

    result = client.post("/notifications/renewal-reminders?days=7", headers=_auth_headers(token))
    assert result.status_code == 200
    data = result.json()
    assert data["sent"] == 1
    assert data["skipped_no_email"] == 1


def test_inactivity_nudge_targets_only_at_risk_members():
    token = _signup("Gym Tau", "tau_owner@example.com", "password123")

    inactive_member = client.post(
        "/members",
        json={"name": "Long Gone", "email": "longgone@example.com"},
        headers=_auth_headers(token),
    ).json()
    _set_join_date(inactive_member["id"], days_ago=30)

    client.post(
        "/members",
        json={"name": "Brand New", "email": "newbie@example.com"},
        headers=_auth_headers(token),
    )

    result = client.post("/notifications/inactivity-nudges?min_level=high", headers=_auth_headers(token))
    assert result.status_code == 200
    data = result.json()
    assert data["sent"] == 1
