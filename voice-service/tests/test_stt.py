import io
import wave
from types import SimpleNamespace

from voice_service.speech.stt import GroqTranscriber, pcm_to_wav

PCM = b"\x01\x00\x02\x00" * 800  # 1,600 samples


def test_pcm_to_wav_describes_16k_mono_pcm16():
    with wave.open(io.BytesIO(pcm_to_wav(PCM)), "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 16_000)
        assert w.getnframes() == 1_600
        assert w.readframes(w.getnframes()) == PCM


async def test_transcriber_sends_wav_file_and_question_prompt():
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
    assert filename == "answer.wav"
    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"


async def test_transcriber_treats_missing_text_as_silence():
    async def transcription(**kwargs):
        return SimpleNamespace(text=None)

    stt = GroqTranscriber(model="m", api_key="k", transcription=transcription)
    assert await stt.transcribe(PCM, prompt="Q") == ""
