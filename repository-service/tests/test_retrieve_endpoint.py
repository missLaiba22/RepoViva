# repository-service/tests/test_retrieve_endpoint.py
"""Endpoint-level tests for POST /internal/v1/repositories/{id}/retrieve.

Same approach as test_ingest_endpoint.py: call the handler function
directly, bypassing HMAC dependency resolution (covered separately by
test_hmac_auth.py). EMBEDDER.embed and search_chunks are monkeypatched so
these tests never touch a real Postgres or Voyage.
"""

from __future__ import annotations

import numpy as np
import pytest

from repository_service.internal import router
from repository_service.internal.router import RetrieveRequestBody, retrieve_chunks

_FAKE_EMBEDDING = np.zeros(4, dtype=np.float32)


async def test_retrieve_returns_chunks_and_forwards_args(monkeypatch) -> None:
    captured: dict = {}

    async def fake_embed(text: str) -> np.ndarray:
        captured["embedded_text"] = text
        return _FAKE_EMBEDDING

    async def fake_search_chunks(pool, **kwargs) -> list[dict]:
        captured["search_kwargs"] = kwargs
        return [
            {
                "id": 1,
                "content": "def foo(): ...",
                "filename": "a.py",
                "start_line": 1,
                "end_line": 1,
                "language": "python",
                "similarity": 0.9,
            },
            {
                "id": 2,
                "content": "def bar(): ...",
                "filename": "b.py",
                "start_line": 5,
                "end_line": 7,
                "language": "python",
                "similarity": 0.8,
            },
        ]

    monkeypatch.setattr(router.EMBEDDER, "embed", fake_embed)
    monkeypatch.setattr(router, "search_chunks", fake_search_chunks)
    monkeypatch.setattr(router, "get_db_pool", lambda: None)

    body = RetrieveRequestBody(
        query="how does auth work?",
        top_k=5,
        filename_prefix="src/",
        exclude_chunk_ids=[10, 11],
    )

    result = await retrieve_chunks(repository_id=42, body=body)

    assert captured["embedded_text"] == "how does auth work?"
    assert len(result["chunks"]) == 2

    search_kwargs = captured["search_kwargs"]
    assert search_kwargs["repository_id"] == "42"
    assert search_kwargs["top_k"] == 5
    assert search_kwargs["filename_prefix"] == "src/"
    assert search_kwargs["exclude_chunk_ids"] == [10, 11]


async def test_retrieve_returns_empty_chunks_when_no_matches(monkeypatch) -> None:
    async def fake_embed(text: str) -> np.ndarray:
        return _FAKE_EMBEDDING

    async def fake_search_chunks(pool, **kwargs) -> list[dict]:
        return []

    monkeypatch.setattr(router.EMBEDDER, "embed", fake_embed)
    monkeypatch.setattr(router, "search_chunks", fake_search_chunks)
    monkeypatch.setattr(router, "get_db_pool", lambda: None)

    body = RetrieveRequestBody(query="anything")
    result = await retrieve_chunks(repository_id=999, body=body)

    assert result == {"chunks": []}


async def test_retrieve_returns_502_when_embedding_fails(monkeypatch) -> None:
    async def fake_embed(text: str) -> np.ndarray:
        raise RuntimeError("voyage is down")

    monkeypatch.setattr(router.EMBEDDER, "embed", fake_embed)

    body = RetrieveRequestBody(query="anything")

    with pytest.raises(Exception) as exc_info:
        await retrieve_chunks(repository_id=1, body=body)

    assert getattr(exc_info.value, "status_code", None) == 502
