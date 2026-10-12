"""Outbound calls to Repository Service, for question planning (decisions 032, 052)."""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx
from repoviva_common.hmac_auth import sign
from repoviva_common.http import get_async_client

from voice_service.config import get_settings

_AREAS_PATH = "/internal/v1/repositories/{repository_id}/areas"
_RETRIEVE_PATH = "/internal/v1/repositories/{repository_id}/retrieve"

# Retrieval embeds the query (one Voyage call) and runs an exact vector
# search (decision 033). Planning runs while the user waits on the live
# page, so a stuck call should fail and be retried, not hang.
_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class Area:
    path: str  # a directory ends with "/"; usable as a filename_prefix
    chunk_count: int


@dataclass(frozen=True)
class Chunk:
    id: int
    content: str
    filename: str
    start_line: int
    end_line: int
    language: str | None
    similarity: float


class RepositoryClient:
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

    async def list_areas(self, repository_id: int, *, limit: int) -> list[Area]:
        """The repository's largest areas, largest first. Raises httpx.HTTPError."""
        url = self._base_url + _AREAS_PATH.format(repository_id=repository_id)
        # A GET has no body, so the signature covers the empty byte string.
        headers = sign(body=b"", secret=self._secret)
        resp = await self._http.get(
            url, params={"limit": limit}, headers=headers, timeout=self._timeout
        )
        resp.raise_for_status()
        return [Area(a["path"], int(a["chunk_count"])) for a in resp.json()["areas"]]

    async def retrieve(
        self,
        repository_id: int,
        query: str,
        *,
        top_k: int,
        filename_prefix: str,
    ) -> list[Chunk]:
        """Top-k chunks for `query` under `filename_prefix`. Raises httpx.HTTPError.

        An empty list is a valid answer (decision 032): the caller decides
        what an area with no matching code means.
        """
        body = {"query": query, "top_k": top_k, "filename_prefix": filename_prefix}
        body_bytes = json.dumps(body, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json", **sign(body=body_bytes, secret=self._secret)}
        url = self._base_url + _RETRIEVE_PATH.format(repository_id=repository_id)

        resp = await self._http.post(url, content=body_bytes, headers=headers, timeout=self._timeout)
        resp.raise_for_status()

        return [
            Chunk(
                id=int(c["id"]),
                content=c["content"],
                filename=c["filename"],
                start_line=int(c["start_line"]),
                end_line=int(c["end_line"]),
                language=c.get("language"),
                similarity=float(c["similarity"]),
            )
            for c in resp.json()["chunks"]
        ]


def get_repository_client() -> RepositoryClient:
    settings = get_settings()
    return RepositoryClient(
        settings.repository_service_base_url, settings.internal_hmac_secret, http=get_async_client()
    )
