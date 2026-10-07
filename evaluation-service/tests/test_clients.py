"""Voice and Repository clients against httpx.MockTransport.

Each handler verifies the HMAC the way the receiving service does.
"""

import json
import time

import httpx
import pytest

from evaluation_service.clients.repository import MAX_IDS_PER_CALL, RepositoryClient
from evaluation_service.clients.voice import Turn, VoiceClient
from evaluation_service.internal.hmac_auth import SIGNATURE_HEADER, TIMESTAMP_HEADER, verify

SECRET = "s3cret"


def assert_signed(request: httpx.Request) -> None:
    verify(
        body=request.content,
        timestamp_header=request.headers.get(TIMESTAMP_HEADER),
        signature_header=request.headers.get(SIGNATURE_HEADER),
        secret=SECRET,
        now=int(time.time()),
    )


async def test_voice_client_gets_signed_turns():
    def handler(request):
        assert_signed(request)
        assert request.method == "GET"
        assert request.url.path == "/internal/v1/interviews/7/turns"
        return httpx.Response(
            200,
            json={
                "turns": [
                    {
                        "seq": 1,
                        "question_text": "Q?",
                        "answer_text": None,
                        "status": "asked",
                        "retrieved_chunk_ids": [4, 9],
                    }
                ]
            },
        )

    client = VoiceClient("http://voice/", SECRET, transport=httpx.MockTransport(handler))

    assert await client.get_turns(7) == [
        Turn(seq=1, question_text="Q?", answer_text=None, status="asked", retrieved_chunk_ids=[4, 9])
    ]


async def test_voice_client_raises_on_error_status():
    client = VoiceClient(
        "http://voice", SECRET, transport=httpx.MockTransport(lambda r: httpx.Response(401))
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.get_turns(7)


async def test_repository_client_batches_dedupes_and_signs():
    bodies: list[list[int]] = []

    def handler(request):
        assert_signed(request)
        assert request.url.path == "/internal/v1/repositories/15/chunks"
        ids = json.loads(request.content)["ids"]
        bodies.append(ids)
        # Pretend id 3 no longer exists.
        return httpx.Response(
            200,
            json={
                "chunks": [
                    {
                        "id": i,
                        "content": "c",
                        "filename": "f.py",
                        "start_line": 1,
                        "end_line": 2,
                        "language": None,
                    }
                    for i in ids
                    if i != 3
                ]
            },
        )

    client = RepositoryClient("http://repo", SECRET, transport=httpx.MockTransport(handler))
    ids = list(range(1, MAX_IDS_PER_CALL + 51)) + [5, 5]

    chunks = await client.get_chunks(15, ids)

    assert [len(b) for b in bodies] == [MAX_IDS_PER_CALL, 50]
    assert 3 not in chunks
    assert len(chunks) == MAX_IDS_PER_CALL + 49
    assert chunks[5].filename == "f.py"
