from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db

TEST_DB_URL = "sqlite:///./test_members.db"
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


def test_staff_can_create_members_but_not_delete():
    owner_token = _signup("Gym Alpha", "alpha_owner@example.com", "password123")

    resp = client.post(
        "/users/staff",
        json={"email": "alpha_staff@example.com", "password": "password123", "role": "staff"},
        headers=_auth_headers(owner_token),
    )
    assert resp.status_code == 200

    login_resp = client.post("/auth/login", data={
        "username": "alpha_staff@example.com",
        "password": "password123",
    })
    assert login_resp.status_code == 200
    staff_token = login_resp.json()["access_token"]

    create_resp = client.post(
        "/members",
        json={"name": "John Doe", "contact": "9999999999"},
        headers=_auth_headers(staff_token),
    )
    assert create_resp.status_code == 200
    member_id = create_resp.json()["id"]

    delete_resp = client.delete(f"/members/{member_id}", headers=_auth_headers(staff_token))
    assert delete_resp.status_code == 403

    delete_resp_owner = client.delete(f"/members/{member_id}", headers=_auth_headers(owner_token))
    assert delete_resp_owner.status_code == 204


def test_tenant_isolation_on_members():
    token_a = _signup("Gym Beta", "beta_owner@example.com", "password123")
    token_b = _signup("Gym Gamma", "gamma_owner@example.com", "password123")

    create_resp = client.post(
        "/members",
        json={"name": "Jane Smith"},
        headers=_auth_headers(token_a),
    )
    assert create_resp.status_code == 200
    member_id = create_resp.json()["id"]

    get_resp = client.get(f"/members/{member_id}", headers=_auth_headers(token_b))
    assert get_resp.status_code == 404

    update_resp = client.put(
        f"/members/{member_id}",
        json={"name": "Hacked Name"},
        headers=_auth_headers(token_b),
    )
    assert update_resp.status_code == 404

    own_get = client.get(f"/members/{member_id}", headers=_auth_headers(token_a))
    assert own_get.status_code == 200
