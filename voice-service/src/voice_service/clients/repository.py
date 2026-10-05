"""Outbound calls to Repository Service: retrieve code chunks (decision 032)."""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from voice_service.config import get_settings
from voice_service.internal.hmac_auth import sign

_RETRIEVE_PATH = "/internal/v1/repositories/{repository_id}/retrieve"

# Retrieval embeds the query (one Voyage call) and runs an exact vector
# search (decision 033). It sits on the turn path, so the timeout is part
# of the 4–5 s budget (decision 006).
_TIMEOUT_SECONDS = 10.0


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
        timeout: float = _TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._secret = secret
        self._timeout = timeout
        self._transport = transport

    async def retrieve(
        self,
        repository_id: int,
        query: str,
        *,
        top_k: int,
        exclude_chunk_ids: list[int] | None = None,
    ) -> list[Chunk]:
        """Top-k chunks for `query`. Raises httpx.HTTPError on any failure.

        An empty list is a valid answer (decision 032): the caller decides
        what an interview with no code context should do.
        """
        body = {
            "query": query,
            "top_k": top_k,
            "exclude_chunk_ids": exclude_chunk_ids or [],
        }
        body_bytes = json.dumps(body, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json", **sign(body=body_bytes, secret=self._secret)}
        url = self._base_url + _RETRIEVE_PATH.format(repository_id=repository_id)

        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            resp = await client.post(url, content=body_bytes, headers=headers)
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
    return RepositoryClient(settings.repository_service_base_url, settings.internal_hmac_secret)
