"""Outbound call to Core API: consume the session token.

HMAC-signed (decision 027). The body is serialized once with fixed
separators so the signed bytes are the sent bytes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from repoviva_common.hmac_auth import sign
from repoviva_common.http import get_async_client

from voice_service.config import get_settings

logger = logging.getLogger(__name__)

_CONSUME_PATH = "/internal/v1/session-tokens/consume"

# Core API's handler is one DB statement; anything slower than this means
# something is wrong, and the user is waiting on the consume.
_TIMEOUT_SECONDS = 5.0


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
        http: httpx.AsyncClient,
        timeout: float = _TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._secret = secret
        self._timeout = timeout
        self._http = http

    async def _post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        body_bytes = json.dumps(body, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json", **sign(body=body_bytes, secret=self._secret)}
        return await self._http.post(
            self._base_url + path, content=body_bytes, headers=headers, timeout=self._timeout
        )

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


def get_core_api_client() -> CoreApiClient:
    settings = get_settings()
    return CoreApiClient(
        settings.core_api_base_url, settings.internal_hmac_secret, http=get_async_client()
    )
