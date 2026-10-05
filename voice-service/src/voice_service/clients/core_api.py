"""Outbound calls to Core API: consume the session token, report the end.

Both are HMAC-signed internal calls (decision 027). Bodies are serialized
once with fixed separators so the signed bytes are the sent bytes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

import httpx

from voice_service.config import get_settings
from voice_service.internal.hmac_auth import sign

logger = logging.getLogger(__name__)

_CONSUME_PATH = "/internal/v1/session-tokens/consume"
_EVENTS_PATH = "/internal/v1/interviews/{interview_id}/events"

# Core API's handlers are one DB statement each; anything slower than
# this means something is wrong, and the user is waiting on the consume.
_TIMEOUT_SECONDS = 5.0

InterviewEventType = Literal["interview.completed", "interview.interrupted"]


@dataclass(frozen=True)
class ConsumedSession:
    """What a successful consume tells us (decision 035)."""

    interview_id: int
    user_id: int
    repository_id: int


class TokenRejectedError(Exception):
    """Core API answered 403. `reason` is for our logs, never the client."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"session token rejected: {reason}")
        self.reason = reason


class CoreApiClient:
    def __init__(
        self,
        base_url: str,
        secret: str,
        *,
        timeout: float = _TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._secret = secret
        self._timeout = timeout
        self._transport = transport

    async def _post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        body_bytes = json.dumps(body, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json", **sign(body=body_bytes, secret=self._secret)}
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            return await client.post(self._base_url + path, content=body_bytes, headers=headers)

    async def consume_token(self, token: str) -> ConsumedSession:
        """Exchange the client's token for its interview (decision 035).

        Raises TokenRejectedError on 403. Any other failure (network,
        5xx, 401 from a secret mismatch) raises httpx.HTTPError — the
        session can't start either way, but it's our fault, not the
        client's, so the caller logs it differently.
        """
        resp = await self._post(_CONSUME_PATH, {"token": token})
        if resp.status_code == 403:
            reason = "unknown"
            try:
                reason = str(resp.json().get("reason", "unknown"))
            except ValueError:
                pass
            raise TokenRejectedError(reason)
        resp.raise_for_status()
        data = resp.json()
        return ConsumedSession(
            interview_id=int(data["interview_id"]),
            user_id=int(data["user_id"]),
            repository_id=int(data["repository_id"]),
        )

    async def send_interview_event(
        self,
        interview_id: int,
        event_type: InterviewEventType,
        *,
        error_message: str | None = None,
    ) -> None:
        """Report the end of a session (decisions 036, 041).

        Best-effort, like Repository Service's ingestion events: logs and
        swallows failures. A lost event leaves the interview stuck
        `active` — the risk decision 036 accepts — but turns are already
        persisted, so nothing is lost.
        """
        body = {
            "event_id": str(uuid4()),
            "event_type": event_type,
            "occurred_at": datetime.now(UTC).isoformat(),
            "data": {"error_message": error_message} if error_message else None,
        }
        try:
            resp = await self._post(_EVENTS_PATH.format(interview_id=interview_id), body)
            resp.raise_for_status()
        except httpx.HTTPError:
            logger.exception(
                "failed to send %s for interview %s (event_id=%s)",
                event_type, interview_id, body["event_id"],
            )


def get_core_api_client() -> CoreApiClient:
    settings = get_settings()
    return CoreApiClient(settings.core_api_base_url, settings.internal_hmac_secret)
