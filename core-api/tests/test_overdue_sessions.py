"""Regression (decision 059): an interview Voice never reported stayed `active` forever."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from core_api.db import engine
from core_api.interviews import service
from core_api.interviews.models import Interview
from core_api.repositories.models import Repository
from core_api.users.models import User


@pytest.fixture
def db():
    """A session whose commits land in savepoints, all rolled back after the test."""
    try:
        connection = engine.connect()
    except OperationalError:
        pytest.skip("Postgres is not running")
    outer = connection.begin()
    connection.execute(text("SELECT 1"))
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


def _interview(db: Session, user: User, repo: Repository, *, started_ago: timedelta) -> Interview:
    now = datetime.now(UTC)
    interview = Interview(
        owner_user_id=user.id,
        repository_id=repo.id,
        status="active",
        session_token_hash=f"hash-{started_ago.total_seconds()}",
        session_token_expires_at=now,
        session_token_consumed_at=now - started_ago,
    )
    db.add(interview)
    db.flush()
    return interview


def test_overdue_active_interview_is_ended_on_read(db):
    user = User(github_user_id=-59, github_login="test-059", encrypted_access_token="x")
    db.add(user)
    db.flush()
    repo = Repository(owner_user_id=user.id, github_url="https://github.com/x/y", status="ready")
    db.add(repo)
    db.flush()
    overdue = _interview(db, user, repo, started_ago=timedelta(hours=1))
    live = _interview(db, user, repo, started_ago=timedelta(minutes=5))

    interviews = service.list_interviews_for_user(db, owner_user_id=user.id)

    by_id = {i.id: i for i in interviews}
    db.refresh(by_id[overdue.id])
    db.refresh(by_id[live.id])
    assert by_id[overdue.id].status == "interrupted"
    assert by_id[overdue.id].error_message == service.OVERDUE_SESSION_MESSAGE
    assert by_id[overdue.id].ended_at is not None
    assert by_id[live.id].status == "active"
