"""GET /internal/v1/interviews/{id}/turns (decision 049), through FastAPI.

Goes through the real HMAC dependency with a signed request; the turn
store and DB pool are faked, so no Postgres is needed.
"""

import time
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from voice_service.config import get_settings
from voice_service.internal import router
from voice_service.internal.hmac_auth import sign
from voice_service.main import app
from voice_service.session.turns import TurnStore

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


class FakeTurnStore:
    requested: ClassVar[list[int]] = []

    def __init__(self, pool):
        pass

    async def list_turns(self, interview_id):
        FakeTurnStore.requested.append(interview_id)
        return TURNS if interview_id == 7 else []


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(router, "TurnStore", FakeTurnStore)
    monkeypatch.setattr(router, "get_db_pool", lambda: None)
    FakeTurnStore.requested = []
    # Not a context manager, so the lifespan (DB pool) doesn't run.
    return TestClient(app)


def _signed_headers(secret: str | None = None) -> dict[str, str]:
    return sign(body=b"", secret=secret or get_settings().internal_hmac_secret)


def test_returns_turns_in_order(client):
    response = client.get("/internal/v1/interviews/7/turns", headers=_signed_headers())

    assert response.status_code == 200
    assert response.json() == {"turns": TURNS}
    assert FakeTurnStore.requested == [7]


def test_unknown_interview_is_empty_200(client):
    response = client.get("/internal/v1/interviews/999/turns", headers=_signed_headers())

    assert response.status_code == 200
    assert response.json() == {"turns": []}


def test_unsigned_request_is_401(client):
    response = client.get("/internal/v1/interviews/7/turns")

    assert response.status_code == 401
    assert FakeTurnStore.requested == []


def test_wrong_secret_is_401(client):
    response = client.get(
        "/internal/v1/interviews/7/turns", headers=_signed_headers("not-the-secret")
    )

    assert response.status_code == 401


def test_stale_signature_is_401(client):
    headers = sign(
        body=b"", secret=get_settings().internal_hmac_secret, timestamp=int(time.time()) - 120
    )
    response = client.get("/internal/v1/interviews/7/turns", headers=headers)

    assert response.status_code == 401


class FakePool:
    """Just enough of asyncpg.Pool for TurnStore.list_turns."""

    def __init__(self, rows):
        self._rows = rows
        self.args = None

    def acquire(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def fetch(self, query, *args):
        self.args = args
        return self._rows


async def test_store_converts_rows_to_plain_dicts():
    # asyncpg returns BIGINT[] as a list already; tuples make sure the store
    # normalises whatever sequence type it gets into JSON-friendly lists.
    pool = FakePool([{**TURNS[0], "retrieved_chunk_ids": (4, 9)}])

    turns = await TurnStore(pool).list_turns(7)

    assert pool.args == (7,)
    assert turns == [TURNS[0]]
