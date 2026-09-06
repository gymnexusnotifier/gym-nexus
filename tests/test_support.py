import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.enums import UserRole
from app.models.gym import Gym
from app.models.support import SupportTicket, TicketPriority, TicketStatus
from app.models.user import User
from app.services.support import change_status, create_ticket, get_ticket_for_user


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_ticket_lifecycle_requires_resolution_and_allows_reopen(db):
    gym = Gym(name="Test gym")
    owner = User(gym=gym, email="owner@example.com", hashed_password="x", role=UserRole.GYM_OWNER)
    admin = User(email="admin@example.com", hashed_password="x", role=UserRole.SUPER_ADMIN)
    db.add_all([gym, owner, admin])
    db.flush()
    ticket = create_ticket(db, owner, "Payment issue", "Payment did not sync", "billing", "high")
    assert ticket.status == TicketStatus.OPEN
    change_status(db, ticket, admin, "in_progress")
    with pytest.raises(Exception, match="resolution message"):
        change_status(db, ticket, admin, "resolved")
    change_status(db, ticket, admin, "resolved", "Payment sync fixed")
    change_status(db, ticket, owner, "reopened")
    assert ticket.status == TicketStatus.REOPENED


def test_owner_cannot_read_another_owner_ticket(db):
    gym_a = Gym(name="A")
    gym_b = Gym(name="B")
    owner_a = User(gym=gym_a, email="a@example.com", hashed_password="x", role=UserRole.GYM_OWNER)
    owner_b = User(gym=gym_b, email="b@example.com", hashed_password="x", role=UserRole.GYM_OWNER)
    db.add_all([gym_a, gym_b, owner_a, owner_b])
    db.flush()
    ticket = create_ticket(db, owner_a, "Private", "Details", "other", "normal")
    assert get_ticket_for_user(db, ticket.id, owner_b) is None