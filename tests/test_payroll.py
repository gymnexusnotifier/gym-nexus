from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.routers import payroll as payroll_router


TEST_DB_URL = "sqlite:///./test_payroll.db"
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


def _signup(email):
    response = client.post("/auth/signup", json={
        "gym_name": "Payroll Test Gym",
        "owner_email": email,
        "owner_password": "password123",
    })
    assert response.status_code == 200
    return response.json()["access_token"]


def test_payroll_release_expenses_and_summary(monkeypatch):
    sent = []
    monkeypatch.setattr(payroll_router, "send_email", lambda *args, **kwargs: sent.append(args) or True)
    token = _signup("payroll_owner@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    staff = client.post("/users/staff", json={
        "email": "trainer@example.com", "password": "password123", "role": "trainer",
    }, headers=headers)
    assert staff.status_code == 200
    staff_id = staff.json()["id"]

    leave = client.post("/leave", json={
        "staff_id": staff_id, "start_date": "2026-08-30", "end_date": "2026-09-02",
        "leave_type": "unpaid",
    }, headers=headers)
    assert leave.status_code == 200

    payload = {
        "staff_id": staff_id, "pay_rate": "30000", "pay_frequency": "monthly",
        "pay_period_start": "2026-09-01", "pay_period_end": "2026-09-30",
        "days_in_period": "30", "other_deductions": "500",
        "other_deductions_note": "Advance adjustment",
    }
    created = client.post("/payroll", json=payload, headers=headers)
    assert created.status_code == 200
    assert created.json()["leave_deduction_amount"] == "2000.00"
    assert created.json()["net_amount"] == "27500.00"

    preview = client.get("/payroll/leave-preview", params={
        "staff_id": staff_id, "pay_period_start": "2026-09-01", "pay_period_end": "2026-09-30",
        "pay_rate": "30000", "days_in_period": "30",
    }, headers=headers)
    assert preview.status_code == 200
    assert preview.json()["unpaid_leave_days"] == "2.00"

    overlap = client.post("/payroll", json=payload, headers=headers)
    assert overlap.status_code == 409

    payroll_id = created.json()["id"]
    released = client.post(f"/payroll/{payroll_id}/release", headers=headers)
    assert released.status_code == 200
    assert released.json()["status"] == "released"
    assert sent
    pdf = client.get(f"/payroll/{payroll_id}/payslip", headers=headers)
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"

    expense = client.post("/payroll/expenses", json={
        "category": "rent", "amount": "8000", "date": date.today().isoformat(), "description": "Studio rent",
    }, headers=headers)
    assert expense.status_code == 200
    expense_id = expense.json()["id"]
    summary = client.get("/payroll/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["total_other_expenses"] == "8000.00"

    deleted = client.delete(f"/payroll/expenses/{expense_id}", headers=headers)
    assert deleted.status_code == 204
    assert client.get("/payroll/expenses", headers=headers).json() == []