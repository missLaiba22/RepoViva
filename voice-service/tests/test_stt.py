import io
import math
import struct
from types import SimpleNamespace

import soundfile as sf

from voice_service.speech.stt import GroqTranscriber, encode_mp3

# One second of a 440 Hz tone: MP3 is lossy, so test with real audio, not
# a repeating byte pattern.
PCM = b"".join(
    struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / 16_000)))
    for i in range(16_000)
)


def test_encode_mp3_is_much_smaller_and_keeps_the_audio():
    mp3 = encode_mp3(PCM)

    assert len(mp3) < len(PCM) / 5
    decoded, rate = sf.read(io.BytesIO(mp3), dtype="int16")
    assert rate == 16_000
    assert abs(len(decoded) - 16_000) < 2_000  # codec padding only


async def test_transcriber_sends_mp3_file_and_question_prompt():
    calls = []

    async def transcription(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text="  It uses asyncpg.  ")

    stt = GroqTranscriber(model="groq/whisper", api_key="k", transcription=transcription)

    assert await stt.transcribe(PCM, prompt="Why asyncpg?") == "It uses asyncpg."
    kwargs = calls[0]
    assert kwargs["model"] == "groq/whisper"
    assert kwargs["api_key"] == "k"
    assert kwargs["prompt"] == "Why asyncpg?"
    filename, data = kwargs["file"]
    assert filename == "answer.mp3"
    assert sf.info(io.BytesIO(data)).format == "MP3"


async def test_transcriber_treats_missing_text_as_silence():
    async def transcription(**kwargs):
        return SimpleNamespace(text=None)

    stt = GroqTranscriber(model="m", api_key="k", transcription=transcription)
    assert await stt.transcribe(PCM, prompt="Q") == ""
