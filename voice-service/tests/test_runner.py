"""The interview loop end to end, with every collaborator faked."""

import asyncio
import json

import httpx
import pytest

from voice_service.clients.core_api import ConsumedSession, TokenRejectedError
from voice_service.clients.repository import Chunk
from voice_service.llm.prompts import OPENING_SEED_QUERY
from voice_service.session.runner import InterviewSession, SessionConfig

SESSION = ConsumedSession(interview_id=7, user_id=2, repository_id=15)
DISCONNECT = object()


class FakeSocket:
    """Scripted client. An exhausted script blocks, like an idle client."""

    def __init__(self, *incoming):
        self._incoming = list(incoming)
        self.sent: list[dict] = []
        self.audio_out: list[bytes] = []
        self.closed: tuple[int, str | None] | None = None

    async def receive(self) -> dict:
        if not self._incoming:
            await asyncio.Event().wait()  # never set
        item = self._incoming.pop(0)
        if item is DISCONNECT:
            return {"type": "websocket.disconnect", "code": 1001}
        if isinstance(item, bytes):
            return {"type": "websocket.receive", "bytes": item}
        return {"type": "websocket.receive", "text": json.dumps(item)}

    async def send_json(self, data):
        self.sent.append(data)

    async def send_bytes(self, data):
        self.audio_out.append(data)

    async def close(self, code=1000, reason=None):
        self.closed = (code, reason)

    def types(self):
        return [m["type"] for m in self.sent]


class FakeCore:
    def __init__(self, consume_result=SESSION):
        self._consume_result = consume_result
        self.events: list[tuple[int, str, str | None]] = []

    async def consume_token(self, token):
        if isinstance(self._consume_result, Exception):
            raise self._consume_result
        return self._consume_result

    async def send_interview_event(self, interview_id, event_type, *, error_message=None):
        self.events.append((interview_id, event_type, error_message))


class FakeRetriever:
    def __init__(self):
        self.calls: list[tuple[str, list[int]]] = []
        self._next_id = 1

    async def retrieve(self, repository_id, query, *, top_k, exclude_chunk_ids):
        self.calls.append((query, list(exclude_chunk_ids)))
        chunk = Chunk(self._next_id, "code", "a.py", 1, 2, "python", 0.9)
        self._next_id += 1
        return [chunk]


class FakeGenerator:
    def __init__(self, fail=False):
        self._fail = fail
        self.histories = []

    async def generate_question(self, history, chunks):
        if self._fail:
            raise RuntimeError("rate limited")
        self.histories.append(list(history))
        return f"Q{len(history) + 1}?"


class FakeTurns:
    def __init__(self):
        self.rows: dict[int, dict] = {}

    async def create_turn(self, *, interview_id, seq, question_text, retrieved_chunk_ids, timings):
        turn_id = len(self.rows) + 100
        self.rows[turn_id] = {"seq": seq, "q": question_text, "ids": retrieved_chunk_ids,
                              "answer": None, "timings": timings}
        return turn_id

    async def record_answer(self, turn_id, answer_text):
        self.rows[turn_id]["answer"] = answer_text


def make(core=None, generator=None, max_questions=2, timeout=1.0):
    parts = {
        "core": core or FakeCore(),
        "retriever": FakeRetriever(),
        "generator": generator or FakeGenerator(),
        "turns": FakeTurns(),
    }
    session = InterviewSession(
        core_api=parts["core"],
        retriever=parts["retriever"],
        generator=parts["generator"],
        turns=parts["turns"],
        config=SessionConfig(max_questions, timeout, retrieval_top_k=6),
    )
    return session, parts


START = {"type": "session.start", "token": "tok"}


def answer(text):
    return {"type": "answer.text", "text": text}


async def test_full_interview_completes_after_question_budget():
    session, p = make(max_questions=2)
    ws = FakeSocket(START, answer("first"), answer("second"))

    await session.run(ws)

    assert ws.types() == [
        "session.ready", "question.text", "turn.complete",
        "question.text", "turn.complete", "session.end",
    ]
    assert ws.sent[-1]["reason"] == "completed"
    assert ws.closed == (1000, None)
    assert p["core"].events == [(7, "interview.completed", None)]
    # Turns persisted with answers and per-stage timings.
    rows = list(p["turns"].rows.values())
    assert [r["answer"] for r in rows] == ["first", "second"]
    assert {"retrieval_ms", "llm_ms"} <= rows[0]["timings"].keys()


async def test_retrieval_uses_seed_then_answer_and_excludes_used_chunks():
    session, p = make(max_questions=2)
    await session.run(FakeSocket(START, answer("because Y"), answer("ok")))

    (q1, ex1), (q2, ex2) = p["retriever"].calls
    assert q1 == OPENING_SEED_QUERY and ex1 == []
    assert q2 == "Q1?\nbecause Y" and ex2 == [1]
    # The second question sees the first exchange.
    assert p["generator"].histories[1][0].answer == "because Y"


async def test_client_session_end_counts_as_completed():
    session, p = make(max_questions=5)
    ws = FakeSocket(START, answer("a"), {"type": "session.end"})

    await session.run(ws)

    assert ws.sent[-1] == {"type": "session.end", "reason": "ended_by_client"}
    assert p["core"].events == [(7, "interview.completed", None)]


async def test_disconnect_mid_interview_is_interrupted():
    session, p = make(max_questions=5)
    await session.run(FakeSocket(START, answer("a"), DISCONNECT))

    assert p["core"].events == [(7, "interview.interrupted", "client disconnected")]
    # The unanswered question is still on record (decision 008).
    assert [r["answer"] for r in p["turns"].rows.values()] == ["a", None]


async def test_llm_failure_is_interrupted_with_error():
    session, p = make(generator=FakeGenerator(fail=True))
    ws = FakeSocket(START)

    await session.run(ws)

    (_, event_type, message), = p["core"].events
    assert event_type == "interview.interrupted"
    assert "rate limited" in message
    assert ws.sent[-1]["type"] == "error"
    assert ws.closed[0] == 1011


@pytest.mark.parametrize(
    "consume_result",
    [TokenRejectedError("expired"), TokenRejectedError("consumed")],
)
async def test_rejected_token_closes_1008_without_event(consume_result):
    session, p = make(core=FakeCore(consume_result))
    ws = FakeSocket(START)

    await session.run(ws)

    assert ws.closed == (1008, "session could not be started")
    assert ws.sent == []  # reason never reaches the client
    assert p["core"].events == []  # never became active


async def test_core_api_down_closes_1011():
    session, p = make(core=FakeCore(httpx.ConnectError("down")))
    ws = FakeSocket(START)

    await session.run(ws)

    assert ws.closed[0] == 1011
    assert p["core"].events == []


async def test_no_session_start_times_out_with_1008():
    session, _ = make(timeout=0.05)
    ws = FakeSocket()  # idle client

    await session.run(ws)

    assert ws.closed == (1008, "session could not be started")


async def test_first_message_must_be_session_start():
    session, _ = make()
    ws = FakeSocket(answer("hi"))

    await session.run(ws)

    assert ws.closed[0] == 1008


async def test_bad_message_mid_interview_gets_error_and_continues():
    session, p = make(max_questions=1)
    ws = FakeSocket(START, {"type": "nope"}, answer("a"))

    await session.run(ws)

    assert "error" in ws.types()
    assert p["core"].events == [(7, "interview.completed", None)]
