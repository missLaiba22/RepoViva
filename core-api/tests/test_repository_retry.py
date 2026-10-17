"""POST /v1/repositories/{id}/retry (decision 061), with the DB session,
current user, repository service and ingestion job faked."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from core_api.auth.dependencies import get_current_user
from core_api.db import get_db
from core_api.main import app
from core_api.repositories import router as repositories_router
from core_api.repositories.ingestion_client import IngestionTriggerError


class FakeDb:
    def refresh(self, _obj):
        pass

    def commit(self):
        pass


def repository(status):
    return SimpleNamespace(
        id=15, github_url="https://github.com/a/b", status=status, owner_user_id=1,
        error_message="fetch failed: x" if status == "failed" else None,
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )


@pytest.fixture
def state(monkeypatch):
    state = {"repo": repository("failed"), "sent": [], "send_error": None}

    def lookup(db, *, repository_id, owner_user_id):
        repo = state["repo"]
        return repo if repo.id == repository_id and owner_user_id == 1 else None

    def restart(db, *, repository_id):
        repo = state["repo"]
        if repo.status != "failed":
            return False
        repo.status, repo.error_message = "queued", None
        return True

    def trigger(**kwargs):
        if state["send_error"]:
            raise IngestionTriggerError(state["send_error"])
        state["sent"].append(kwargs)

    monkeypatch.setattr(repositories_router.service, "get_repository_for_user", lookup)
    monkeypatch.setattr(repositories_router.service, "restart_failed_ingestion", restart)
    monkeypatch.setattr(repositories_router, "trigger_ingestion", trigger)
    return state


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = lambda: FakeDb()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_failed_repository_is_queued_and_the_job_sent_again(client, state):
    response = client.post("/v1/repositories/15/retry")

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["error_message"] is None
    assert state["sent"] == [{"repository_id": 15, "github_url": "https://github.com/a/b"}]


@pytest.mark.parametrize("status", ["queued", "in_progress", "ready"])
def test_other_repositories_are_returned_as_is(client, state, status):
    state["repo"] = repository(status)

    response = client.post("/v1/repositories/15/retry")

    assert response.status_code == 200
    assert response.json()["status"] == status
    assert state["sent"] == []


def test_job_that_cannot_be_sent_leaves_it_failed(client, state):
    state["send_error"] = "queue down"

    response = client.post("/v1/repositories/15/retry")

    assert response.json()["status"] == "failed"


def test_someone_elses_repository_is_not_found(client, state):
    assert client.post("/v1/repositories/99/retry").status_code == 404
