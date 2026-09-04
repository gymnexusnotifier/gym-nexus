from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db
from app.models.member import Member

TEST_DB_URL = "sqlite:///./test_churn.db"
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


def test_churn_risk_flags_long_inactive_member_high():
    token = _signup("Gym Lambda", "lambda_owner@example.com", "password123")

    member_resp = client.post("/members", json={"name": "Old Inactive Member"}, headers=_auth_headers(token))
    member_id = member_resp.json()["id"]
    _set_join_date(member_id, days_ago=30)  # joined a month ago, never checked in

    risk_resp = client.get(f"/churn/{member_id}", headers=_auth_headers(token))
    assert risk_resp.status_code == 200
    assert risk_resp.json()["risk_level"] == "high"

    at_risk = client.get("/churn/at-risk", headers=_auth_headers(token))
    assert at_risk.status_code == 200
    assert any(r["member_id"] == member_id for r in at_risk.json())


def test_brand_new_member_is_low_risk():
    token = _signup("Gym Mu", "mu_owner@example.com", "password123")

    member_resp = client.post("/members", json={"name": "Brand New Member"}, headers=_auth_headers(token))
    member_id = member_resp.json()["id"]

    risk_resp = client.get(f"/churn/{member_id}", headers=_auth_headers(token))
    assert risk_resp.status_code == 200
    assert risk_resp.json()["risk_level"] == "low"


def test_churn_risk_respects_tenant_isolation():
    token_a = _signup("Gym Nu", "nu_owner@example.com", "password123")
    token_b = _signup("Gym Xi", "xi_owner@example.com", "password123")

    member_resp = client.post("/members", json={"name": "Gym Nu Member"}, headers=_auth_headers(token_a))
    member_id = member_resp.json()["id"]

    cross_resp = client.get(f"/churn/{member_id}", headers=_auth_headers(token_b))
    assert cross_resp.status_code == 404
