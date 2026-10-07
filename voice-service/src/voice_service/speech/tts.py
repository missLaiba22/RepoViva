"""Text-to-speech via Deepgram Aura-2, streamed (decision 044).

Deepgram starts sending audio before it has synthesized the whole
sentence. Reading the HTTP response as a stream and yielding each chunk
as it arrives lets the client start playing early: time to *first* audio
is what decision 006's latency target measures.

Output is raw PCM16 mono at 24 kHz with no container, so every chunk is
playable on its own — no header to wait for or parse.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from voice_service.config import get_settings

SAMPLE_RATE = 24_000

_SPEAK_URL = "https://api.deepgram.com/v1/speak"

# Connect + time between chunks, not the whole stream: a long question
# legitimately streams for several seconds.
_TIMEOUT_SECONDS = 10.0


class TtsError(Exception):
    """Deepgram refused the request; the message carries its reason."""


class DeepgramSynthesizer:
    def __init__(
        self,
        *,
        api_key: str,
        voice: str,
        timeout: float = _TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._voice = voice
        self._timeout = timeout
        self._transport = transport

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        """Yield PCM16 24 kHz mono audio for `text`, chunk by chunk.

        Errors propagate (decision 044 → `interrupted`).
        """
        params = {
            "model": self._voice,
            "encoding": "linear16",
            "sample_rate": str(SAMPLE_RATE),
            "container": "none",
        }
        headers = {"Authorization": f"Token {self._api_key}"}

        async with (
            httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client,
            client.stream(
                "POST", _SPEAK_URL, params=params, headers=headers, json={"text": text}
            ) as resp,
        ):
            if resp.is_error:
                # A streamed body isn't read yet; read it for Deepgram's reason.
                body = (await resp.aread()).decode(errors="replace")[:300]
                raise TtsError(f"Deepgram {resp.status_code}: {body}")
            async for chunk in resp.aiter_bytes():
                if chunk:
                    yield chunk


def get_synthesizer() -> DeepgramSynthesizer:
    settings = get_settings()
    return DeepgramSynthesizer(api_key=settings.deepgram_api_key, voice=settings.tts_voice)
