"""POST/GET /internal/v1/reports (decision 049), through FastAPI.

Goes through the real HMAC dependency with signed requests. The store is
an in-memory fake and generation is recorded instead of run, so no
Postgres or LLM is needed.
"""

import json
import time

import pytest
from fastapi.testclient import TestClient

from evaluation_service.config import get_settings
from evaluation_service.internal import router
from evaluation_service.internal.hmac_auth import sign
from evaluation_service.main import app
from evaluation_service.reports import PendingReport
from tests.fakes import FakeReportStore


@pytest.fixture
def store():
    return FakeReportStore()


@pytest.fixture
def scheduled(monkeypatch):
    runs: list[PendingReport] = []

    async def record(report):
        runs.append(report)

    monkeypatch.setattr(router, "run_generation", record)
    return runs


@pytest.fixture
def client(monkeypatch, store, scheduled):
    monkeypatch.setattr(router, "ReportStore", lambda pool: store)
    monkeypatch.setattr(router, "get_db_pool", lambda: None)
    # Not a context manager, so the lifespan (DB pool, resume) doesn't run.
    return TestClient(app)


def _signed(body: bytes = b"", secret: str | None = None) -> dict[str, str]:
    return sign(body=body, secret=secret or get_settings().internal_hmac_secret)


def trigger(client, interview_id=7, repository_id=15, outcome="completed", headers=None):
    body = json.dumps(
        {"interview_id": interview_id, "repository_id": repository_id, "outcome": outcome}
    ).encode()
    return client.post(
        "/internal/v1/reports",
        content=body,
        headers={"Content-Type": "application/json", **(headers or _signed(body))},
    )


def test_trigger_schedules_new_report(client, store, scheduled):
    response = trigger(client)

    assert response.status_code == 202
    assert response.json() == {"interview_id": 7, "status": "generating", "scheduled": True}
    assert scheduled == [PendingReport(interview_id=7, repository_id=15, partial=False)]
    assert store.rows[7]["status"] == "generating"


def test_interrupted_interview_is_partial(client, scheduled):
    trigger(client, outcome="interrupted")

    assert scheduled[0].partial is True


@pytest.mark.parametrize("existing", ["generating", "ready"])
def test_trigger_is_noop_while_generating_or_ready(client, store, scheduled, existing):
    store.rows[7] = {"interview_id": 7, "repository_id": 15, "partial": False, "status": existing}

    response = trigger(client)

    assert response.status_code == 202
    assert response.json() == {"interview_id": 7, "status": existing, "scheduled": False}
    assert scheduled == []


def test_trigger_regenerates_failed_report(client, store, scheduled):
    store.rows[7] = {"interview_id": 7, "repository_id": 15, "partial": False, "status": "failed"}

    response = trigger(client)

    assert response.json()["scheduled"] is True
    assert store.rows[7]["status"] == "generating"
    assert len(scheduled) == 1


def test_repeated_trigger_schedules_once(client, scheduled):
    trigger(client)
    trigger(client)

    assert len(scheduled) == 1


def test_unknown_outcome_is_422(client, scheduled):
    response = trigger(client, outcome="active")

    assert response.status_code == 422
    assert scheduled == []


def test_unsigned_trigger_is_401(client, store, scheduled):
    response = trigger(client, headers={"X-Unsigned": "1"})

    assert response.status_code == 401
    assert store.rows == {}
    assert scheduled == []


def test_trigger_signed_over_other_body_is_401(client, scheduled):
    # A valid signature for a different interview must not authorise this one.
    other = json.dumps({"interview_id": 8, "repository_id": 15, "outcome": "completed"}).encode()

    response = trigger(client, headers=_signed(other))

    assert response.status_code == 401


def test_get_report(client, store):
    store.rows[7] = {"interview_id": 7, "status": "ready", "summary": {"average_clarity": 3.5}}

    response = client.get("/internal/v1/reports/7", headers=_signed())

    assert response.status_code == 200
    assert response.json() == store.rows[7]


def test_get_missing_report_is_404(client):
    response = client.get("/internal/v1/reports/999", headers=_signed())

    assert response.status_code == 404


def test_get_with_wrong_secret_is_401(client, store):
    store.rows[7] = {"interview_id": 7, "status": "ready"}

    response = client.get("/internal/v1/reports/7", headers=_signed(secret="not-the-secret"))

    assert response.status_code == 401


def test_get_with_stale_signature_is_401(client):
    headers = sign(
        body=b"", secret=get_settings().internal_hmac_secret, timestamp=int(time.time()) - 120
    )

    response = client.get("/internal/v1/reports/7", headers=headers)

    assert response.status_code == 401
