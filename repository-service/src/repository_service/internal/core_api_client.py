# repository-service/src/repository_service/internal/core_api_client.py
"""Outbound HTTP client: fires ingestion-status callbacks at Core API.

Every request is HMAC-signed with the shared internal secret (decision 027).
Best-effort: emit_event logs exceptions on failure but does not retry —
retry/dedup are deliberately deferred (see slice 3 close-out of decision 028).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

from repository_service.config import get_settings
from repository_service.internal.hmac_auth import sign

logger = logging.getLogger(__name__)

_EVENTS_PATH = "/internal/v1/repositories/{repository_id}/events"

# Timeout on a single event POST. Kept modest — Core API's handler is
# a DB write and a state check, no external calls, so anything longer
# than this suggests something is wrong.
_TIMEOUT_SECONDS = 5.0


class CoreApiClient:
    """Emits ingestion-status events to Core API.

    Constructed once per orchestrator run (or per process — either works;
    httpx.AsyncClient is created fresh per call for simplicity). Injectable
    transport for tests.
    """

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

    async def emit_event(
        self,
        repository_id: str,
        event_type: str,
        *,
        data: dict[str, Any] | None = None,
    ) -> None:
        """POST a single ingestion event to Core API.

        Never raises on network/HTTP failures — logs the exception and
        returns. Failed callbacks are visible in logs, and the next event
        in the sequence has a chance of getting through. Retry infrastructure
        will be added when observed drop rates justify it.

        The event body is what Core API's IngestionEventBody schema expects:
        event_id (uuid), event_type, occurred_at (ISO 8601 UTC), data (dict).
        """
        event_id = str(uuid4())
        occurred_at = datetime.now(UTC).isoformat()

        body_dict = {
            "event_id": event_id,
            "event_type": event_type,
            "occurred_at": occurred_at,
            "data": data,
        }
        # Deterministic serialization — the signature covers the exact
        # bytes we send. `separators=(",", ":")` strips optional whitespace
        # so we never sign one byte-sequence and send a different one.
        body_bytes = json.dumps(body_dict, separators=(",", ":")).encode()

        signed = sign(body=body_bytes, secret=self._secret)
        headers = {"Content-Type": "application/json", **signed.as_dict()}

        url = self._base_url + _EVENTS_PATH.format(repository_id=repository_id)

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                resp = await client.post(url, content=body_bytes, headers=headers)
                resp.raise_for_status()
        except httpx.HTTPError:
            # Best-effort — log and swallow. The alternative (raising)
            # would kill the orchestrator's ability to keep going, which
            # is worse than a lost status update.
            logger.exception(
                "failed to emit event %s for repository %s (event_id=%s)",
                event_type, repository_id, event_id,
            )


def get_core_api_client() -> CoreApiClient:
    """Factory used by the orchestrator — reads settings once per call."""
    settings = get_settings()
    return CoreApiClient(settings.core_api_base_url, settings.internal_hmac_secret)