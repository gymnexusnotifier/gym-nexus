from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db

TEST_DB_URL = "sqlite:///./test_dashboard.db"
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


def test_dashboard_summary_and_peak_hours_and_isolation():
    token_a = _signup("Gym Theta", "theta_owner@example.com", "password123")
    token_b = _signup("Gym Iota", "iota_owner@example.com", "password123")

    plan_resp = client.post(
        "/plans",
        json={"name": "Monthly", "price": "1000.00", "duration_days": 30},
        headers=_auth_headers(token_a),
    )
    plan_id = plan_resp.json()["id"]

    member_resp = client.post(
        "/members",
        json={"name": "Rahul Verma"},
        headers=_auth_headers(token_a),
    )
    member_id = member_resp.json()["id"]

    client.post(
        "/payments",
        json={"member_id": member_id, "plan_id": plan_id, "amount": "1000.00"},
        headers=_auth_headers(token_a),
    )

    checkin_resp = client.post(
        "/attendance/check-in",
        json={"member_id": member_id},
        headers=_auth_headers(token_a),
    )
    assert checkin_resp.status_code == 200

    summary = client.get("/dashboard/summary", headers=_auth_headers(token_a))
    assert summary.status_code == 200
    data = summary.json()
    assert data["today_checkins"] == 1
    assert data["active_members"] == 1
    assert float(data["monthly_revenue"]) == 1000.0

    peak = client.get("/dashboard/peak-hours", headers=_auth_headers(token_a))
    assert peak.status_code == 200
    assert sum(entry["checkins"] for entry in peak.json()) == 1

    summary_b = client.get("/dashboard/summary", headers=_auth_headers(token_b))
    assert summary_b.status_code == 200
    data_b = summary_b.json()
    assert data_b["today_checkins"] == 0
    assert data_b["active_members"] == 0


def test_member_status_and_inactive_filters():
    token = _signup("Gym Kappa", "kappa_owner@example.com", "password123")

    m1 = client.post("/members", json={"name": "Active Member"}, headers=_auth_headers(token)).json()
    m2 = client.post("/members", json={"name": "Frozen Member"}, headers=_auth_headers(token)).json()

    client.put(f"/members/{m2['id']}", json={"status": "frozen"}, headers=_auth_headers(token))

    frozen_list = client.get("/members?status=frozen", headers=_auth_headers(token))
    assert frozen_list.status_code == 200
    assert len(frozen_list.json()) == 1
    assert frozen_list.json()[0]["id"] == m2["id"]

    inactive_list = client.get("/members?inactive_days=0", headers=_auth_headers(token))
    assert inactive_list.status_code == 200
    returned_ids = {m["id"] for m in inactive_list.json()}
    assert m1["id"] in returned_ids
    assert m2["id"] in returned_ids
