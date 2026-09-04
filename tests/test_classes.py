from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db

TEST_DB_URL = "sqlite:///./test_classes.db"
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


def _login(email, password):
    resp = client.post("/auth/login", data={"username": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_class_creation_trainer_view_and_capacity_limit():
    owner_token = _signup("Gym Omicron", "omicron_owner@example.com", "password123")

    trainer_resp = client.post(
        "/users/staff",
        json={"email": "omicron_trainer@example.com", "password": "password123", "role": "trainer"},
        headers=_auth_headers(owner_token),
    )
    assert trainer_resp.status_code == 200
    trainer_id = trainer_resp.json()["id"]

    class_resp = client.post(
        "/classes",
        json={
            "name": "Morning Yoga",
            "trainer_id": trainer_id,
            "day_of_week": 0,
            "start_time": "07:00",
            "duration_minutes": 45,
            "capacity": 1,
        },
        headers=_auth_headers(owner_token),
    )
    assert class_resp.status_code == 200
    class_id = class_resp.json()["id"]

    trainer_token = _login("omicron_trainer@example.com", "password123")
    mine_resp = client.get("/classes/mine", headers=_auth_headers(trainer_token))
    assert mine_resp.status_code == 200
    assert len(mine_resp.json()) == 1
    assert mine_resp.json()[0]["id"] == class_id

    member1 = client.post("/members", json={"name": "Member One"}, headers=_auth_headers(owner_token)).json()
    member2 = client.post("/members", json={"name": "Member Two"}, headers=_auth_headers(owner_token)).json()

    book1 = client.post(
        f"/classes/{class_id}/book", json={"member_id": member1["id"]}, headers=_auth_headers(owner_token)
    )
    assert book1.status_code == 200

    book2 = client.post(
        f"/classes/{class_id}/book", json={"member_id": member2["id"]}, headers=_auth_headers(owner_token)
    )
    assert book2.status_code == 400  # capacity is 1

    dup_book = client.post(
        f"/classes/{class_id}/book", json={"member_id": member1["id"]}, headers=_auth_headers(owner_token)
    )
    assert dup_book.status_code == 400  # already booked

    bookings = client.get(f"/classes/{class_id}/bookings", headers=_auth_headers(owner_token))
    assert bookings.status_code == 200
    assert len(bookings.json()) == 1


def test_class_tenant_isolation():
    token_a = _signup("Gym Pi", "pi_owner@example.com", "password123")
    token_b = _signup("Gym Rho", "rho_owner@example.com", "password123")

    class_resp = client.post(
        "/classes",
        json={"name": "HIIT", "day_of_week": 1, "start_time": "18:00"},
        headers=_auth_headers(token_a),
    )
    assert class_resp.status_code == 200
    class_id = class_resp.json()["id"]

    get_resp = client.get(f"/classes/{class_id}", headers=_auth_headers(token_b))
    assert get_resp.status_code == 404
