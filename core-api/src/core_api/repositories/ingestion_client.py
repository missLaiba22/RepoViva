"""HTTP client for calling Repository Service's ingest endpoint.

This module owns the outbound trigger call — the sender side of the
Core API → Repository Service contract. Kept out of the router (which
speaks HTTP incoming) and out of the service layer (which speaks SQL).
Everything about how we sign, format, and send the trigger lives here.
"""

from __future__ import annotations

import json

import httpx

from core_api.config import get_settings
from core_api.security.hmac_auth import sign


class IngestionTriggerError(Exception):
    """Raised when the trigger call to Repository Service fails.

    Wraps both network errors (timeouts, connection refused) and HTTP
    errors (non-2xx responses). The router turns this into a user-visible
    'ingestion could not start' state on the repository row.
    """


# Default HTTP timeout. Kept modest — the trigger endpoint on Repository
# Service is expected to return 202 almost immediately (accept work, return).
# If it hangs longer than this, something is wrong and we'd rather fail
# fast than block the user's POST /v1/repositories response.
_TIMEOUT_SECONDS = 5.0


def trigger_ingestion(*, repository_id: int, github_url: str) -> None:
    """Fire the ingest trigger to Repository Service.

    Raises IngestionTriggerError on any failure — network error, timeout,
    or non-2xx response. On success, returns None.

    Note: this is fire-and-forget from Core API's perspective. Repository
    Service returns 202 Accepted and does the real work asynchronously.
    We don't wait for ingestion to complete — that's what the (deferred)
    callback protocol is for (see decision 028).
    """
    settings = get_settings()
    url = (
        f"{settings.repository_service_base_url.rstrip('/')}"
        f"/internal/v1/repositories/{repository_id}/ingest"
    )
    body_dict = {"github_url": github_url}
    # Serialize deterministically so the signature covers the exact bytes
    # we send. `separators=(",", ":")` removes optional whitespace so we
    # never sign one byte-sequence and send a slightly different one.
    body_bytes = json.dumps(body_dict, separators=(",", ":")).encode()

    headers = {"Content-Type": "application/json"}
    headers.update(sign(body=body_bytes, secret=settings.internal_hmac_secret).as_dict())

    try:
        response = httpx.post(url, content=body_bytes, headers=headers, timeout=_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise IngestionTriggerError(f"could not reach Repository Service: {exc}") from exc

    if response.status_code >= 300:
        raise IngestionTriggerError(
            f"Repository Service returned {response.status_code}: {response.text[:200]}"
        )