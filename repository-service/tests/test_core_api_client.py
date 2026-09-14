# repository-service/tests/test_core_api_client.py
"""Tests for CoreApiClient — the outbound event sender.

Uses httpx.MockTransport to intercept the actual request the client
constructs. This lets us verify the URL, headers, and body shape are
correct end-to-end without hitting a real Core API. Since MockTransport
sits at the transport layer, everything above it (retries, timeouts,
HMAC signing, JSON encoding) runs for real.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest

from repository_service.internal.core_api_client import CoreApiClient


_SECRET = "test-secret-32-chars-or-so-long"


async def test_emit_event_posts_signed_request_to_correct_url() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = request.content
        return httpx.Response(202, json={"status": "accepted"})

    client = CoreApiClient(
        base_url="http://core-api.test",
        secret=_SECRET,
        transport=httpx.MockTransport(handler),
    )

    await client.emit_event(
        "42",
        "ingestion.started",
        data={"note": "kickoff"},
    )

    # URL and method
    assert captured["method"] == "POST"
    assert captured["url"] == "http://core-api.test/internal/v1/repositories/42/events"

    # Body shape — parse back and check the fields the receiver reads.
    payload = json.loads(captured["body"])
    assert payload["event_type"] == "ingestion.started"
    assert payload["data"] == {"note": "kickoff"}
    # event_id is a UUID, occurred_at is an ISO timestamp — we don't
    # pin their exact values, but we check they're present and stringy.
    assert isinstance(payload["event_id"], str) and len(payload["event_id"]) > 0
    assert isinstance(payload["occurred_at"], str) and len(payload["occurred_at"]) > 0

    # HMAC signature — recompute independently and compare.
    ts = captured["headers"]["x-repoviva-timestamp"]
    sig_header = captured["headers"]["x-repoviva-signature"]
    assert sig_header.startswith("sha256=")
    received_digest = sig_header[len("sha256="):]

    expected = hmac.new(
        _SECRET.encode(),
        f"{ts}.".encode() + captured["body"],
        hashlib.sha256,
    ).hexdigest()
    assert received_digest == expected


async def test_emit_event_swallows_http_errors_silently() -> None:
    """A non-2xx response must not raise — the orchestrator can't stop
    ingestion just because a callback failed. Log-and-swallow is the
    contract."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    client = CoreApiClient(
        base_url="http://core-api.test",
        secret=_SECRET,
        transport=httpx.MockTransport(handler),
    )

    # Must not raise.
    await client.emit_event("42", "ingestion.started")


async def test_emit_event_swallows_network_errors_silently() -> None:
    """Same contract when the network itself fails."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = CoreApiClient(
        base_url="http://core-api.test",
        secret=_SECRET,
        transport=httpx.MockTransport(handler),
    )

    # Must not raise.
    await client.emit_event("42", "ingestion.started")