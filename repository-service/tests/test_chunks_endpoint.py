# repository-service/tests/test_chunks_endpoint.py
"""Tests for POST /internal/v1/repositories/{id}/chunks (decision 049).

Same approach as test_retrieve_endpoint.py: call the handler directly,
bypassing HMAC (covered by test_hmac_auth.py), with the DB call
monkeypatched. The lookup's SQL arguments are checked with a fake pool.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from repository_service.internal import router
from repository_service.internal.router import ChunksByIdBody, get_chunks
from repository_service.retrieval.lookup import get_chunks_by_ids

CHUNK = {
    "id": 4,
    "content": "def place_order(): ...",
    "filename": "orders/service.py",
    "start_line": 10,
    "end_line": 30,
    "language": "python",
}


async def test_chunks_returns_lookup_result_and_forwards_args(monkeypatch) -> None:
    captured: dict = {}

    async def fake_get_chunks_by_ids(pool, **kwargs) -> list[dict]:
        captured.update(kwargs)
        return [CHUNK]

    monkeypatch.setattr(router, "get_chunks_by_ids", fake_get_chunks_by_ids)
    monkeypatch.setattr(router, "get_db_pool", lambda: None)

    result = await get_chunks(repository_id=42, body=ChunksByIdBody(ids=[4, 9]))

    assert result == {"chunks": [CHUNK]}
    # repository_id is TEXT in code_chunks, as for /retrieve.
    assert captured == {"repository_id": "42", "ids": [4, 9]}


@pytest.mark.parametrize("ids", [[], list(range(201))])
def test_body_rejects_empty_or_oversized_id_list(ids) -> None:
    with pytest.raises(ValidationError):
        ChunksByIdBody(ids=ids)


def test_body_accepts_max_id_list() -> None:
    assert len(ChunksByIdBody(ids=list(range(200))).ids) == 200


class FakePool:
    def __init__(self, rows):
        self._rows = rows
        self.call = None

    async def fetch(self, query, *args):
        self.call = (query, args)
        return self._rows


async def test_lookup_scopes_by_repository_and_returns_dicts() -> None:
    pool = FakePool([CHUNK])

    chunks = await get_chunks_by_ids(pool, repository_id="42", ids=[4, 9])

    query, args = pool.call
    assert args == ("42", [4, 9])
    assert "repository_id = $1" in query
    assert "similarity" not in query
    assert chunks == [CHUNK]
