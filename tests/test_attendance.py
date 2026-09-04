from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db

TEST_DB_URL = "sqlite:///./test_attendance.db"
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


def test_checkin_dedupes_same_day_and_isolates_tenants():
    token_a = _signup("Gym Delta", "delta_owner@example.com", "password123")
    token_b = _signup("Gym Epsilon", "epsilon_owner@example.com", "password123")

    member_resp = client.post(
        "/members",
        json={"name": "Amit Kumar"},
        headers=_auth_headers(token_a),
    )
    assert member_resp.status_code == 200
    member_id = member_resp.json()["id"]

    checkin1 = client.post("/attendance/check-in", json={"member_id": member_id}, headers=_auth_headers(token_a))
    assert checkin1.status_code == 200
    record_id_1 = checkin1.json()["id"]

    checkin2 = client.post("/attendance/check-in", json={"member_id": member_id}, headers=_auth_headers(token_a))
    assert checkin2.status_code == 200
    assert checkin2.json()["id"] == record_id_1

    today_list = client.get("/attendance/today", headers=_auth_headers(token_a))
    assert today_list.status_code == 200
    assert len(today_list.json()) == 1

    cross_checkin = client.post("/attendance/check-in", json={"member_id": member_id}, headers=_auth_headers(token_b))
    assert cross_checkin.status_code == 404
