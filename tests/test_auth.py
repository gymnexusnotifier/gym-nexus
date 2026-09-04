from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db

TEST_DB_URL = "sqlite:///./test.db"
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


def test_signup_login_and_tenant_scoping():
    resp_a = client.post("/auth/signup", json={
        "gym_name": "Gym A",
        "owner_email": "ownerA@example.com",
        "owner_password": "password123",
    })
    assert resp_a.status_code == 200
    token_a = resp_a.json()["access_token"]

    resp_b = client.post("/auth/signup", json={
        "gym_name": "Gym B",
        "owner_email": "ownerB@example.com",
        "owner_password": "password123",
    })
    assert resp_b.status_code == 200
    token_b = resp_b.json()["access_token"]

    me_a = client.get("/auth/me", headers={"Authorization": f"Bearer {token_a}"})
    me_b = client.get("/auth/me", headers={"Authorization": f"Bearer {token_b}"})

    assert me_a.status_code == 200
    assert me_b.status_code == 200
    assert me_a.json()["gym_id"] != me_b.json()["gym_id"]
