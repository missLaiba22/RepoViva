"""The report trigger after an end event, and GET /v1/interviews/{id}/report.

Through FastAPI, with the DB session, current user, interview service and
Evaluation Service client faked: no Postgres or other services needed.
"""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from core_api.auth.dependencies import get_current_user
from core_api.config import get_settings
from core_api.db import get_db
from core_api.internal import router as internal_router
from core_api.interviews import evaluation_client
from core_api.interviews import router as interviews_router
from core_api.main import app
from core_api.security.hmac_auth import sign

READY = {
    "interview_id": 7,
    "status": "ready",
    "partial": False,
    "model": "groq/openai/gpt-oss-120b",
    "prompt_version": "v5",
    "summary": {"average_correctness": 3.5},
    "turn_evaluations": [{"seq": 1, "status": "graded"}],
    "error_message": None,
    "created_at": "2026-10-08T10:00:00+00:00",
    "completed_at": "2026-10-08T10:01:30+00:00",
}


def interview(status="completed", owner=1):
    return SimpleNamespace(id=7, repository_id=15, status=status, owner_user_id=owner)


class FakeEvaluation:
    """Stands in for evaluation_client's two calls."""

    def __init__(self, report=None, error=None):
        self.report = report
        self.error = error
        self.triggers: list[dict] = []

    def get_report(self, interview_id):
        if self.error:
            raise evaluation_client.EvaluationServiceError(self.error)
        return self.report

    def trigger_report(self, **kwargs):
        self.triggers.append(kwargs)


@pytest.fixture
def evaluation(monkeypatch):
    fake = FakeEvaluation()
    monkeypatch.setattr(evaluation_client, "get_report", fake.get_report)
    monkeypatch.setattr(evaluation_client, "trigger_report", fake.trigger_report)
    return fake


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def owned(monkeypatch):
    """The current user's interview 7, in whatever state the test sets."""
    state = {"interview": interview()}

    def lookup(db, *, interview_id, owner_user_id):
        found = state["interview"]
        if found and found.id == interview_id and found.owner_user_id == owner_user_id:
            return found
        return None

    monkeypatch.setattr(interviews_router.service, "get_interview_for_user", lookup)
    return state


# --- GET /v1/interviews/{id}/report ------------------------------------------


def test_ready_report_is_200_without_error_text(client, owned, evaluation):
    evaluation.report = READY

    response = client.get("/v1/interviews/7/report")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["summary"] == READY["summary"]
    assert body["turn_evaluations"] == READY["turn_evaluations"]
    assert "error_message" not in body
    assert evaluation.triggers == []


def test_failed_report_is_200_and_not_regenerated(client, owned, evaluation):
    evaluation.report = {
        **READY,
        "status": "failed",
        "summary": None,
        "turn_evaluations": None,
        "error_message": "ConnectError: All connection attempts failed",
    }

    response = client.get("/v1/interviews/7/report")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert "ConnectError" not in response.text
    assert evaluation.triggers == []


def test_generating_report_is_202(client, owned, evaluation):
    evaluation.report = {
        **READY,
        "status": "generating",
        "summary": None,
        "turn_evaluations": None,
        "completed_at": None,
    }

    response = client.get("/v1/interviews/7/report")

    assert response.status_code == 202
    assert response.json()["status"] == "generating"


def test_missing_report_is_retriggered_and_202(client, owned, evaluation):
    owned["interview"] = interview(status="interrupted")

    response = client.get("/v1/interviews/7/report")

    assert response.status_code == 202
    assert response.json()["status"] == "generating"
    assert evaluation.triggers == [
        {"interview_id": 7, "repository_id": 15, "outcome": "interrupted"}
    ]


@pytest.mark.parametrize("status", ["created", "active"])
def test_interview_not_ended_is_404(client, owned, evaluation, status):
    owned["interview"] = interview(status=status)

    response = client.get("/v1/interviews/7/report")

    assert response.status_code == 404
    assert evaluation.triggers == []


def test_someone_elses_interview_is_404(client, owned, evaluation):
    owned["interview"] = interview(owner=2)
    evaluation.report = READY

    response = client.get("/v1/interviews/7/report")

    assert response.status_code == 404
    assert response.json() == {"detail": "Interview not found"}


def test_evaluation_unavailable_is_503(client, owned, evaluation):
    evaluation.error = "could not reach Evaluation Service"

    response = client.get("/v1/interviews/7/report")

    assert response.status_code == 503


# --- POST /v1/interviews/{id}/report/retry ----------------------------------


def test_retry_regenerates_a_failed_report(client, owned, evaluation):
    evaluation.report = {**READY, "status": "failed", "summary": None, "turn_evaluations": None}

    response = client.post("/v1/interviews/7/report/retry")

    assert response.status_code == 202
    assert response.json()["status"] == "generating"
    assert evaluation.triggers == [{"interview_id": 7, "repository_id": 15, "outcome": "completed"}]


def test_retry_with_no_report_triggers_one(client, owned, evaluation):
    response = client.post("/v1/interviews/7/report/retry")

    assert response.status_code == 202
    assert len(evaluation.triggers) == 1


def test_retry_leaves_a_ready_report_alone(client, owned, evaluation):
    evaluation.report = READY

    response = client.post("/v1/interviews/7/report/retry")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert evaluation.triggers == []


@pytest.mark.parametrize("status", ["created", "active"])
def test_retry_before_the_interview_ends_is_404(client, owned, evaluation, status):
    owned["interview"] = interview(status=status)

    assert client.post("/v1/interviews/7/report/retry").status_code == 404
    assert evaluation.triggers == []


def test_retry_someone_elses_interview_is_404(client, owned, evaluation):
    owned["interview"] = interview(owner=2)

    assert client.post("/v1/interviews/7/report/retry").status_code == 404


def test_retry_with_evaluation_down_is_503(client, owned, evaluation):
    evaluation.error = "connect failed"

    assert client.post("/v1/interviews/7/report/retry").status_code == 503


def test_not_logged_in_is_401(owned, evaluation):
    app.dependency_overrides[get_db] = lambda: None
    try:
        response = TestClient(app).get("/v1/interviews/7/report")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


# --- Trigger after the end event ---------------------------------------------


def _post_event(client, event_type):
    body = json.dumps(
        {
            "event_id": "6f1c1f9e-4d4b-4c4a-9a43-3f0f6f3b2b11",
            "event_type": event_type,
            "occurred_at": "2026-10-08T12:00:00Z",
        }
    ).encode()
    headers = sign(body=body, secret=get_settings().internal_hmac_secret).as_dict()
    return client.post(
        "/internal/v1/interviews/7/events",
        content=body,
        headers={"Content-Type": "application/json", **headers},
    )


@pytest.fixture
def triggers(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(internal_router, "trigger_report_logged", lambda **kw: sent.append(kw))
    return sent


@pytest.mark.parametrize(
    ("event_type", "outcome"),
    [("interview.completed", "completed"), ("interview.interrupted", "interrupted")],
)
def test_end_event_triggers_report(client, monkeypatch, triggers, event_type, outcome):
    monkeypatch.setattr(
        internal_router.interviews_service,
        "apply_interview_event",
        lambda db, **kw: interview(status=outcome),
    )

    response = _post_event(client, event_type)

    assert response.status_code == 202
    assert triggers == [{"interview_id": 7, "repository_id": 15, "outcome": outcome}]


def test_rejected_end_event_sends_no_trigger(client, monkeypatch, triggers):
    def already_ended(db, **kw):
        raise internal_router.interviews_service.IllegalTransitionError("already ended")

    monkeypatch.setattr(
        internal_router.interviews_service, "apply_interview_event", already_ended
    )

    response = _post_event(client, "interview.completed")

    assert response.status_code == 422
    assert triggers == []
