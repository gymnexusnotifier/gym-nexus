from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db

TEST_DB_URL = "sqlite:///./test_payments.db"
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


def test_payment_computes_due_date_and_generates_receipt():
    token_a = _signup("Gym Zeta", "zeta_owner@example.com", "password123")
    token_b = _signup("Gym Eta", "eta_owner@example.com", "password123")

    plan_resp = client.post(
        "/plans",
        json={"name": "Monthly", "price": "1000.00", "duration_days": 30},
        headers=_auth_headers(token_a),
    )
    assert plan_resp.status_code == 200
    plan_id = plan_resp.json()["id"]

    member_resp = client.post(
        "/members",
        json={"name": "Priya Sharma"},
        headers=_auth_headers(token_a),
    )
    assert member_resp.status_code == 200
    member_id = member_resp.json()["id"]

    payment_resp = client.post(
        "/payments",
        json={"member_id": member_id, "plan_id": plan_id, "amount": "1000.00"},
        headers=_auth_headers(token_a),
    )
    assert payment_resp.status_code == 200
    payment = payment_resp.json()
    expected_due = (date.today() + timedelta(days=30)).isoformat()
    assert payment["next_due_date"] == expected_due
    payment_id = payment["id"]

    renewals = client.get("/payments/upcoming-renewals?days=60", headers=_auth_headers(token_a))
    assert renewals.status_code == 200
    assert any(r["member_id"] == member_id for r in renewals.json())

    receipt = client.get(f"/payments/{payment_id}/receipt", headers=_auth_headers(token_a))
    assert receipt.status_code == 200
    assert receipt.headers["content-type"] == "application/pdf"
    assert receipt.content[:4] == b"%PDF"

    cross_get = client.get(f"/payments/{payment_id}/receipt", headers=_auth_headers(token_b))
    assert cross_get.status_code == 404
