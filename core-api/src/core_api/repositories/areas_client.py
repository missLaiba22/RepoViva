"""Core API's side of Repository Service's areas query (decision 065)."""

from __future__ import annotations

import httpx
from repoviva_common.hmac_auth import sign
from repoviva_common.http import get_sync_client

from core_api.config import get_settings

# Voice Service's default MAX_QUESTIONS: with the same limit, these are the
# areas the question plan uses (decision 060).
AREA_LIMIT = 6

_TIMEOUT_SECONDS = 5.0


class RepositoryServiceError(Exception):
    """Repository Service couldn't be read."""


def get_areas(repository_id: int, *, http: httpx.Client | None = None) -> list[dict]:
    """The repository's areas, largest first; empty before it is indexed."""
    settings = get_settings()
    headers = sign(body=b"", secret=settings.internal_hmac_secret)
    try:
        response = (http or get_sync_client()).get(
            f"{settings.repository_service_base_url.rstrip('/')}"
            f"/internal/v1/repositories/{repository_id}/areas",
            params={"limit": AREA_LIMIT},
            headers=headers,
            timeout=_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise RepositoryServiceError(f"could not reach Repository Service: {exc}") from exc

    if response.status_code != 200:
        raise RepositoryServiceError(
            f"Repository Service returned {response.status_code}: {response.text[:200]}"
        )
    return response.json()["areas"]
