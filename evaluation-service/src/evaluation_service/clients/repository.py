"""Outbound call to Repository Service: code chunks by id (decision 049)."""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from evaluation_service.config import get_settings
from evaluation_service.internal.hmac_auth import sign

_CHUNKS_PATH = "/internal/v1/repositories/{repository_id}/chunks"

# Repository Service's per-call limit on `ids`.
MAX_IDS_PER_CALL = 200

_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class Chunk:
    id: int
    content: str
    filename: str
    start_line: int
    end_line: int
    language: str | None


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

    async def get_chunks(self, repository_id: int, ids: list[int]) -> dict[int, Chunk]:
        """Chunks by id. Ids with no row are absent from the result.

        Splits into calls of MAX_IDS_PER_CALL. Raises httpx.HTTPError on
        any failure.
        """
        unique = sorted(set(ids))
        url = self._base_url + _CHUNKS_PATH.format(repository_id=repository_id)
        found: dict[int, Chunk] = {}
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            for start in range(0, len(unique), MAX_IDS_PER_CALL):
                batch = unique[start : start + MAX_IDS_PER_CALL]
                body = json.dumps({"ids": batch}, separators=(",", ":")).encode()
                headers = {
                    "Content-Type": "application/json",
                    **sign(body=body, secret=self._secret),
                }
                resp = await client.post(url, content=body, headers=headers)
                resp.raise_for_status()
                for c in resp.json()["chunks"]:
                    chunk = Chunk(
                        id=int(c["id"]),
                        content=c["content"],
                        filename=c["filename"],
                        start_line=int(c["start_line"]),
                        end_line=int(c["end_line"]),
                        language=c.get("language"),
                    )
                    found[chunk.id] = chunk
        return found


def get_repository_client() -> RepositoryClient:
    settings = get_settings()
    return RepositoryClient(settings.repository_service_base_url, settings.internal_hmac_secret)
