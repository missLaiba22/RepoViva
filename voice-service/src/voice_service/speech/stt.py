"""Speech-to-text via Groq Whisper through litellm (decisions 043, 047).

The client streams raw PCM (decision 045). Raw PCM is large — 32 KB per
second — and the first live interview showed STT time growing with
answer length because the upload dominated. So the buffered answer is
compressed to a low-bitrate MP3 (about 10x smaller, same transcript)
before it is sent as one request.
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import litellm
import numpy as np
import soundfile as sf

from voice_service.config import get_settings

logger = logging.getLogger(__name__)

# Client audio format (decision 045).
SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2  # bytes: PCM16
CHANNELS = 1
BYTES_PER_SECOND = SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS

# libsndfile's 0..1 scale; 0.9 is a low bitrate that's plenty for speech.
# Measured on a 94 s answer: 3.0 MB → 0.33 MB, transcript unchanged.
_MP3_COMPRESSION_LEVEL = 0.9

# Whisper reads at most ~224 tokens of prompt; a question is well under.
_MAX_PROMPT_CHARS = 800

# litellm.atranscription's shape; injectable so tests never call a provider.
Transcription = Callable[..., Awaitable[Any]]


def encode_mp3(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Compress raw PCM16 mono to MP3."""
    samples = np.frombuffer(pcm, dtype="<i2")
    buf = io.BytesIO()
    sf.write(
        buf, samples, sample_rate,
        format="MP3", subtype="MPEG_LAYER_III", compression_level=_MP3_COMPRESSION_LEVEL,
    )
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
        # Encoding is CPU work (~0.4 s for a 90 s answer). Run on the event
        # loop, it would freeze every other interview on this process for
        # that long; a worker thread keeps the loop free.
        t0 = time.perf_counter()
        audio = await asyncio.to_thread(encode_mp3, pcm)
        logger.info(
            "encoded %.1fs of audio: %d -> %d bytes in %dms",
            len(pcm) / BYTES_PER_SECOND, len(pcm), len(audio),
            round((time.perf_counter() - t0) * 1000),
        )
        response = await self._transcription(
            model=self._model,
            api_key=self._api_key,
            # Groq infers the format from the filename's extension.
            file=("answer.mp3", audio),
            prompt=prompt[:_MAX_PROMPT_CHARS],
            language="en",
        )
        return (response.text or "").strip()


def get_transcriber() -> GroqTranscriber:
    settings = get_settings()
    return GroqTranscriber(model=settings.stt_model, api_key=settings.groq_api_key)
