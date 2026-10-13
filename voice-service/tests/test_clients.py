"""Core API and Repository Service clients, against httpx.MockTransport.

MockTransport sits below the client, so URL building, JSON encoding and
HMAC signing all run for real.
"""

import hashlib
import hmac
import json

import httpx
import pytest

from voice_service.clients.core_api import (
    ConsumedSession,
    CoreApiClient,
    TokenRejectedError,
)
from voice_service.clients.repository import Area, RepositoryClient

_SECRET = "test-secret"


def _assert_signed(request: httpx.Request) -> None:
    ts = request.headers["X-Repoviva-Timestamp"]
    expected = hmac.new(
        _SECRET.encode(), f"{ts}.".encode() + request.content, hashlib.sha256
    ).hexdigest()
    assert request.headers["X-Repoviva-Signature"] == f"sha256={expected}"


def _core(handler) -> CoreApiClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return CoreApiClient("http://core.test/", _SECRET, http=http)


async def test_consume_token_returns_session():
    def handler(request):
        assert request.url.path == "/internal/v1/session-tokens/consume"
        assert json.loads(request.content) == {"token": "tok"}
        _assert_signed(request)
        return httpx.Response(200, json={"interview_id": 7, "user_id": 2, "repository_id": 15})

    assert await _core(handler).consume_token("tok") == ConsumedSession(7, 2, 15)


async def test_consume_token_403_carries_reason():
    client = _core(lambda r: httpx.Response(403, json={"reason": "consumed"}))
    with pytest.raises(TokenRejectedError) as exc:
        await client.consume_token("tok")
    assert exc.value.reason == "consumed"


async def test_consume_token_other_errors_are_http_errors():
    client = _core(lambda r: httpx.Response(401, json={"detail": "unauthorized"}))
    with pytest.raises(httpx.HTTPStatusError):
        await client.consume_token("tok")


def _repo(handler) -> RepositoryClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return RepositoryClient("http://repo.test", _SECRET, http=http)


async def test_list_areas_sends_limit_and_parses_areas():
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/internal/v1/repositories/15/areas"
        assert request.url.params["limit"] == "6"
        _assert_signed(request)
        return httpx.Response(200, json={"areas": [{"path": "core-api/", "chunk_count": 40}]})

    assert await _repo(handler).list_areas(15, limit=6) == [Area("core-api/", 40)]


async def test_retrieve_sends_prefix_and_parses_chunks():
    def handler(request):
        assert request.url.path == "/internal/v1/repositories/15/retrieve"
        assert json.loads(request.content) == {
            "query": "q", "top_k": 2, "filename_prefix": "app/",
        }
        _assert_signed(request)
        return httpx.Response(200, json={"chunks": [{
            "id": 3, "content": "def f(): ...", "filename": "app/main.py",
            "start_line": 1, "end_line": 2, "language": "python", "similarity": 0.8,
        }]})

    chunks = await _repo(handler).retrieve(15, "q", top_k=2, filename_prefix="app/")
    assert [c.id for c in chunks] == [3]
    assert chunks[0].filename == "app/main.py"
