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
from voice_service.clients.repository import RepositoryClient

_SECRET = "test-secret"


def _assert_signed(request: httpx.Request) -> None:
    ts = request.headers["X-Repoviva-Timestamp"]
    expected = hmac.new(
        _SECRET.encode(), f"{ts}.".encode() + request.content, hashlib.sha256
    ).hexdigest()
    assert request.headers["X-Repoviva-Signature"] == f"sha256={expected}"


def _core(handler) -> CoreApiClient:
    return CoreApiClient("http://core.test/", _SECRET, transport=httpx.MockTransport(handler))


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


async def test_interview_event_body_matches_core_api_envelope():
    captured = {}

    def handler(request):
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        _assert_signed(request)
        return httpx.Response(202)

    await _core(handler).send_interview_event(
        7, "interview.interrupted", error_message="socket closed"
    )
    assert captured["path"] == "/internal/v1/interviews/7/events"
    body = captured["body"]
    assert body["event_type"] == "interview.interrupted"
    assert body["data"] == {"error_message": "socket closed"}
    assert {"event_id", "occurred_at"} <= body.keys()


async def test_interview_event_failure_is_swallowed():
    def handler(request):
        raise httpx.ConnectError("down")

    # Must not raise: the session is already over.
    await _core(handler).send_interview_event(7, "interview.completed")


async def test_retrieve_sends_exclusions_and_parses_chunks():
    def handler(request):
        assert request.url.path == "/internal/v1/repositories/15/retrieve"
        assert json.loads(request.content) == {
            "query": "q", "top_k": 6, "exclude_chunk_ids": [1, 2],
        }
        _assert_signed(request)
        return httpx.Response(200, json={"chunks": [{
            "id": 3, "content": "def f(): ...", "filename": "app/main.py",
            "start_line": 1, "end_line": 2, "language": "python", "similarity": 0.8,
        }]})

    client = RepositoryClient("http://repo.test", _SECRET, transport=httpx.MockTransport(handler))
    chunks = await client.retrieve(15, "q", top_k=6, exclude_chunk_ids=[1, 2])
    assert [c.id for c in chunks] == [3]
    assert chunks[0].filename == "app/main.py"
