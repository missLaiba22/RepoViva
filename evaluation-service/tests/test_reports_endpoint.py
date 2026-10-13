"""GET /internal/v1/reports/{id} (decision 049), through FastAPI.

Goes through the real HMAC dependency with signed requests. The store is
an in-memory fake, so no Postgres is needed.
"""

import time

import pytest
from fastapi.testclient import TestClient
from repoviva_common.hmac_auth import sign

from evaluation_service.config import get_settings
from evaluation_service.internal import router
from evaluation_service.main import app
from tests.fakes import FakeReportStore


@pytest.fixture
def store():
    return FakeReportStore()


@pytest.fixture
def client(monkeypatch, store):
    monkeypatch.setattr(router, "ReportStore", lambda pool: store)
    monkeypatch.setattr(router, "get_db_pool", lambda: None)
    # Not a context manager, so the lifespan (DB pool) doesn't run.
    return TestClient(app)


def _signed(body: bytes = b"", secret: str | None = None) -> dict[str, str]:
    return sign(body=body, secret=secret or get_settings().internal_hmac_secret)


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
