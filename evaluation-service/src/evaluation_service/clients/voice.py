"""Outbound call to Voice Service: an interview's turns (decision 049)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from evaluation_service.config import get_settings
from evaluation_service.internal.hmac_auth import sign

_TURNS_PATH = "/internal/v1/interviews/{interview_id}/turns"

# One indexed SELECT on Voice's side. Generation is in the background, so
# this only bounds how long a broken Voice Service can hold a report.
_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class Turn:
    seq: int
    question_text: str
    answer_text: str | None
    status: str  # 'asked' | 'answered'
    retrieved_chunk_ids: list[int]


class VoiceClient:
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

    async def get_turns(self, interview_id: int) -> list[Turn]:
        """Turns ordered by seq. Raises httpx.HTTPError on any failure."""
        url = self._base_url + _TURNS_PATH.format(interview_id=interview_id)
        # A GET has no body, so the signature covers the empty byte string.
        headers = sign(body=b"", secret=self._secret)
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return [
            Turn(
                seq=int(t["seq"]),
                question_text=t["question_text"],
                answer_text=t["answer_text"],
                status=t["status"],
                retrieved_chunk_ids=[int(i) for i in t["retrieved_chunk_ids"]],
            )
            for t in resp.json()["turns"]
        ]


def get_voice_client() -> VoiceClient:
    settings = get_settings()
    return VoiceClient(settings.voice_service_base_url, settings.internal_hmac_secret)
