"""The question plan through Core API (decisions 052, 057): the job sent on
create, the status proxy with its lazy re-trigger, and the retry.

Through FastAPI, with the DB session, current user, interview service and
Voice Service client faked.
"""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from core_api.auth.dependencies import get_current_user
from core_api.config import get_settings
from core_api.db import get_db
from core_api.interviews import router as interviews_router
from core_api.interviews import service, voice_client
from core_api.main import app


def interview(status="created", owner=1):
    return SimpleNamespace(
        id=7, repository_id=15, status=status, owner_user_id=owner, error_message=None,
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC), ended_at=None,
        session_token_expires_at=datetime.now(UTC), session_token_consumed_at=None,
    )


def plan(status, retryable=None):
    return {"interview_id": 7, "plan_status": status, "error_message": None,
            "retryable": retryable}


class FakeVoice:
    def __init__(self):
        self.plan = None
        self.error = None
        self.requested: list[dict] = []

    def get_plan_status(self, interview_id):
        if self.error:
            raise voice_client.VoiceServiceError(self.error)
        return self.plan

    def request_plan(self, **kwargs):
        if self.error:
            raise voice_client.VoiceServiceError(self.error)
        self.requested.append(kwargs)


@pytest.fixture
def voice(monkeypatch):
    fake = FakeVoice()
    monkeypatch.setattr(voice_client, "get_plan_status", fake.get_plan_status)
    monkeypatch.setattr(voice_client, "request_plan", fake.request_plan)
    return fake


@pytest.fixture
def owned(monkeypatch):
    state = {"interview": interview()}

    def lookup(db, *, interview_id, owner_user_id):
        found = state["interview"]
        if found.id == interview_id and found.owner_user_id == owner_user_id:
            return found
        return None

    monkeypatch.setattr(interviews_router.service, "get_interview_for_user", lookup)
    return state


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_plan_job_contract(monkeypatch):
    sent = []
    monkeypatch.setattr(voice_client, "send_job", lambda q, t, d: sent.append((q, t, d)))

    voice_client.request_plan(interview_id=7, repository_id=15)

    assert sent == [(get_settings().planning_jobs_queue_url, "plan.requested",
                     {"interview_id": 7, "repository_id": 15})]


# --- POST /v1/interviews -----------------------------------------------------


def _create(client, monkeypatch):
    created = SimpleNamespace(interview=interview(), raw_token="tok")
    monkeypatch.setattr(service, "create_interview", lambda db, **kw: created)
    return client.post("/v1/interviews", json={"repository_id": 15})


def test_create_sends_the_plan_job(client, voice, monkeypatch):
    response = _create(client, monkeypatch)

    assert response.status_code == 201
    assert voice.requested == [{"interview_id": 7, "repository_id": 15}]


def test_create_succeeds_when_the_plan_job_cannot_be_sent(client, voice, monkeypatch):
    voice.error = "queue down"

    assert _create(client, monkeypatch).status_code == 201


# --- GET /v1/interviews/{id}/plan --------------------------------------------


def test_plan_status_is_proxied(client, owned, voice):
    voice.plan = plan("failed", retryable=False)

    response = client.get("/v1/interviews/7/plan")

    assert response.status_code == 200
    assert response.json() == plan("failed", retryable=False)
    assert voice.requested == []


def test_missing_plan_is_requested_again(client, owned, voice):
    response = client.get("/v1/interviews/7/plan")

    assert response.json()["plan_status"] == "generating"
    assert voice.requested == [{"interview_id": 7, "repository_id": 15}]


def test_missing_plan_after_the_interview_started_is_404(client, owned, voice):
    owned["interview"] = interview(status="active")

    assert client.get("/v1/interviews/7/plan").status_code == 404
    assert voice.requested == []


def test_plan_of_someone_elses_interview_is_404(client, owned, voice):
    owned["interview"] = interview(owner=2)

    assert client.get("/v1/interviews/7/plan").status_code == 404


def test_voice_down_is_503(client, owned, voice):
    voice.error = "down"

    assert client.get("/v1/interviews/7/plan").status_code == 503


# --- POST /v1/interviews/{id}/plan/retry -------------------------------------


@pytest.mark.parametrize("current", [None, plan("failed", retryable=True)])
def test_retry_requests_a_missing_or_retryable_plan(client, owned, voice, current):
    voice.plan = current

    response = client.post("/v1/interviews/7/plan/retry")

    assert response.json()["plan_status"] == "generating"
    assert len(voice.requested) == 1


@pytest.mark.parametrize(
    "current", [plan("generating"), plan("ready"), plan("failed", retryable=False)]
)
def test_retry_leaves_other_plans_alone(client, owned, voice, current):
    voice.plan = current

    response = client.post("/v1/interviews/7/plan/retry")

    assert response.json() == current
    assert voice.requested == []


def test_retry_after_the_interview_started_is_409(client, owned, voice):
    owned["interview"] = interview(status="active")

    assert client.post("/v1/interviews/7/plan/retry").status_code == 409
