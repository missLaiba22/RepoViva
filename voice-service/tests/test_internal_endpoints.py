"""Internal endpoints (decisions 049, 052), through FastAPI.

Goes through the real HMAC dependency with signed requests; the session
store is faked, so no MongoDB is needed.
"""

import time

import pytest
from fastapi.testclient import TestClient
from repoviva_common.hmac_auth import sign

from voice_service.config import get_settings
from voice_service.internal import router
from voice_service.main import app
from voice_service.session.store import PlanState

TURNS = [
    {
        "seq": 1,
        "question_text": "What happens when two users buy the last item?",
        "answer_text": "The order service locks the row.",
        "status": "answered",
        "retrieved_chunk_ids": [4, 9],
    },
    {
        "seq": 2,
        "question_text": "And if the payment webhook is late?",
        "answer_text": None,
        "status": "asked",
        "retrieved_chunk_ids": [12],
    },
]


class FakeStore:
    """Interview 7 has a ready plan and two turns; others have nothing."""

    async def get_plan_state(self, interview_id):
        return PlanState(plan_status="ready") if interview_id == 7 else None

    async def list_turns(self, interview_id):
        return TURNS if interview_id == 7 else []


@pytest.fixture
def store(monkeypatch):
    fake = FakeStore()
    monkeypatch.setattr(router, "SessionStore", lambda db: fake)
    monkeypatch.setattr(router, "get_db", lambda: None)
    return fake


@pytest.fixture
def client(store):
    # Not a context manager, so the lifespan (MongoDB) doesn't run.
    return TestClient(app)


def _signed(body: bytes = b"", secret: str | None = None) -> dict[str, str]:
    return sign(body=body, secret=secret or get_settings().internal_hmac_secret)


# --- GET /plan ----------------------------------------------------------------


def test_plan_status_shape(client):
    response = client.get("/internal/v1/interviews/7/plan", headers=_signed())

    assert response.status_code == 200
    assert response.json() == {
        "interview_id": 7, "plan_status": "ready", "error_message": None, "retryable": None,
    }


def test_plan_status_unknown_interview_is_404(client):
    response = client.get("/internal/v1/interviews/999/plan", headers=_signed())

    assert response.status_code == 404


# --- GET /turns (decision 049; the shape Evaluation Service reads) -------------


def test_returns_turns_in_order(client):
    response = client.get("/internal/v1/interviews/7/turns", headers=_signed())

    assert response.status_code == 200
    assert response.json() == {"turns": TURNS}


def test_unknown_interview_is_empty_200(client):
    response = client.get("/internal/v1/interviews/999/turns", headers=_signed())

    assert response.status_code == 200
    assert response.json() == {"turns": []}


def test_unsigned_request_is_401(client):
    assert client.get("/internal/v1/interviews/7/turns").status_code == 401


def test_wrong_secret_is_401(client):
    response = client.get("/internal/v1/interviews/7/turns", headers=_signed(secret="nope"))

    assert response.status_code == 401


def test_stale_signature_is_401(client):
    headers = sign(
        body=b"", secret=get_settings().internal_hmac_secret, timestamp=int(time.time()) - 120
    )
    response = client.get("/internal/v1/interviews/7/turns", headers=headers)

    assert response.status_code == 401
