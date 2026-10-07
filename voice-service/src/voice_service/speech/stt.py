"""Speech-to-text via Groq Whisper through litellm (decision 043).

The client streams raw PCM (decision 045). Whisper wants an audio *file*,
so the buffered answer is wrapped in a WAV header — 44 bytes that say
"16-bit, mono, 16 kHz" — and sent as one request.
"""

from __future__ import annotations

import io
import wave
from collections.abc import Awaitable, Callable
from typing import Any

import litellm

from voice_service.config import get_settings

# Client audio format (decision 045).
SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2  # bytes: PCM16
CHANNELS = 1
BYTES_PER_SECOND = SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS

# Whisper reads at most ~224 tokens of prompt; a question is well under.
_MAX_PROMPT_CHARS = 800

# litellm.atranscription's shape; injectable so tests never call a provider.
Transcription = Callable[..., Awaitable[Any]]


def pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Wrap raw PCM16 mono in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(SAMPLE_WIDTH)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


class GroqTranscriber:
    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        transcription: Transcription = litellm.atranscription,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._transcription = transcription

    async def transcribe(self, pcm: bytes, *, prompt: str) -> str:
        """Transcript of one answer; "" if Whisper heard nothing.

        `prompt` is the question just asked: Whisper uses it as preceding
        context, which biases spelling toward the identifiers in it.
        Provider errors propagate (decision 041 → `interrupted`).
        """
        response = await self._transcription(
            model=self._model,
            api_key=self._api_key,
            # Groq infers the format from the filename's extension.
            file=("answer.wav", pcm_to_wav(pcm)),
            prompt=prompt[:_MAX_PROMPT_CHARS],
            language="en",
        )
        return (response.text or "").strip()


def get_transcriber() -> GroqTranscriber:
    settings = get_settings()
    return GroqTranscriber(model=settings.stt_model, api_key=settings.groq_api_key)
