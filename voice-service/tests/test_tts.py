"""Deepgram synthesizer against httpx.MockTransport."""

import json

import httpx
import pytest

from voice_service.speech.tts import DeepgramSynthesizer, TtsError


async def _body(*chunks):
    for chunk in chunks:
        yield chunk


def _synth(handler):
    return DeepgramSynthesizer(api_key="dg", voice="aura-2-x",
                               transport=httpx.MockTransport(handler))


async def test_synthesize_requests_raw_pcm_and_yields_chunks():
    def handler(request):
        assert request.url.path == "/v1/speak"
        assert dict(request.url.params) == {
            "model": "aura-2-x", "encoding": "linear16",
            "sample_rate": "24000", "container": "none",
        }
        assert request.headers["authorization"] == "Token dg"
        assert json.loads(request.content) == {"text": "Why?"}
        # An async generator body arrives as separate chunks, like a real stream.
        return httpx.Response(200, content=_body(b"ab", b"", b"cd"))

    chunks = [c async for c in _synth(handler).synthesize("Why?")]
    assert chunks == [b"ab", b"cd"]


async def test_synthesize_error_carries_deepgram_reason():
    def handler(request):
        return httpx.Response(402, json={"err_msg": "insufficient credit"})

    with pytest.raises(TtsError, match="402.*insufficient credit"):
        [c async for c in _synth(handler).synthesize("Why?")]
