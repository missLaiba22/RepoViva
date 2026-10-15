"""The interview loop end to end, with every collaborator faked."""

import asyncio
import json

import httpx
import pytest

from voice_service.clients.core_api import ConsumedSession, TokenRejectedError
from voice_service.session.runner import InterviewSession, SessionConfig
from voice_service.session.store import PlannedQuestion

SESSION = ConsumedSession(interview_id=7, user_id=2, repository_id=15)
DISCONNECT = object()


def planned(n):
    return [
        PlannedQuestion(seq=i, area=f"area{i}/", topic=f"topic {i}", text=f"Q{i}?", chunk_ids=[i])
        for i in range(1, n + 1)
    ]


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

    async def consume_token(self, token):
        if isinstance(self._consume_result, Exception):
            raise self._consume_result
        return self._consume_result



class FakeEvents:
    def __init__(self):
        self.events: list[tuple[int, str, str | None]] = []
        self.repository_ids: list[int] = []

    async def interview_ended(self, *, interview_id, repository_id, outcome, error_message=None):
        self.events.append((interview_id, outcome, error_message))
        self.repository_ids.append(repository_id)


class FakeTranscriber:
    """Returns scripted transcripts in order; an Exception item is raised."""

    def __init__(self, *transcripts):
        self._transcripts = list(transcripts)
        self.calls: list[tuple[bytes, str]] = []

    async def transcribe(self, pcm, *, prompt):
        self.calls.append((pcm, prompt))
        result = self._transcripts.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeSynthesizer:
    """Yields two audio chunks per question, or fails after the first."""

    def __init__(self, fail=False):
        self._fail = fail
        self.texts: list[str] = []

    async def synthesize(self, text):
        self.texts.append(text)
        yield b"aud1-" + text.encode()
        if self._fail:
            raise RuntimeError("deepgram 402")
        yield b"aud2"


class FakeSessions:
    """The session document's questions, keyed by seq. plan=None: not ready."""

    def __init__(self, plan):
        self._plan = plan
        self.questions = {
            q.seq: {"status": "planned", "answer": None, "timings": {}} for q in plan or []
        }

    async def load_plan(self, interview_id):
        return self._plan

    async def mark_asked(self, interview_id, seq):
        self.questions[seq]["status"] = "asked"

    async def record_answer(self, interview_id, seq, answer):
        self.questions[seq] |= {"status": "answered", "answer": answer}

    async def add_timings(self, interview_id, seq, timings):
        self.questions[seq]["timings"] |= timings


def make(core=None, transcriber=None, synthesizer=None, plan=..., timeout=1.0,
         max_answer_seconds=180, max_session_seconds=1800):
    parts = {
        "core": core or FakeCore(),
        "events": FakeEvents(),
        "transcriber": transcriber or FakeTranscriber(),
        "synthesizer": synthesizer or FakeSynthesizer(),
        "sessions": FakeSessions(planned(2) if plan is ... else plan),
    }
    session = InterviewSession(
        core_api=parts["core"],
        events=parts["events"],
        transcriber=parts["transcriber"],
        synthesizer=parts["synthesizer"],
        sessions=parts["sessions"],
        config=SessionConfig(
            timeout,
            max_answer_seconds=max_answer_seconds,
            max_session_seconds=max_session_seconds,
        ),
    )
    return session, parts


START = {"type": "session.start", "token": "tok"}
AUDIO_END = {"type": "audio.end"}
PCM = b"\x01\x00" * 160  # 10 ms of 16 kHz PCM16


def answer(text):
    return {"type": "answer.text", "text": text}


def statuses(p):
    return [(q["status"], q["answer"]) for q in p["sessions"].questions.values()]


async def test_full_interview_plays_the_plan_in_order():
    session, p = make(plan=planned(2))
    ws = FakeSocket(START, answer("first"), answer("second"))

    await session.run(ws)

    assert ws.types() == [
        "session.ready", "question.text", "question.audio_end", "turn.complete",
        "question.text", "question.audio_end", "turn.complete", "session.end",
    ]
    assert [m["text"] for m in ws.sent if m["type"] == "question.text"] == ["Q1?", "Q2?"]
    assert ws.sent[-1]["reason"] == "completed"
    assert ws.closed == (1000, None)
    assert p["events"].events == [(7, "completed", None)]
    assert p["events"].repository_ids == [15]  # in the event, so Evaluation needn't call back
    assert statuses(p) == [("answered", "first"), ("answered", "second")]


async def test_messages_carry_seq():
    session, _ = make(plan=planned(1))
    ws = FakeSocket(START, answer("a"))

    await session.run(ws)

    assert ws.sent[1] == {"type": "question.text", "seq": 1, "text": "Q1?"}
    assert ws.sent[2] == {"type": "question.audio_end", "seq": 1}
    assert ws.sent[3] == {"type": "turn.complete", "seq": 1}


async def test_plan_not_ready_is_interrupted_and_closed():
    session, p = make(plan=None)
    ws = FakeSocket(START)

    await session.run(ws)

    assert ws.types() == ["error"]
    assert ws.sent[0]["code"] == "plan_not_ready"
    assert ws.closed[0] == 1008
    assert p["events"].events == [(7, "interrupted", "plan not ready")]


async def test_client_session_end_counts_as_completed():
    session, p = make(plan=planned(5))
    ws = FakeSocket(START, answer("a"), {"type": "session.end"})

    await session.run(ws)

    assert ws.sent[-1] == {"type": "session.end", "reason": "ended_by_client"}
    assert p["events"].events == [(7, "completed", None)]


async def test_disconnect_mid_interview_is_interrupted():
    session, p = make(plan=planned(5))
    await session.run(FakeSocket(START, answer("a"), DISCONNECT))

    assert p["events"].events == [(7, "interrupted", "client disconnected")]
    # The unanswered question is still on record (decision 008).
    assert statuses(p)[:3] == [("answered", "a"), ("asked", None), ("planned", None)]


async def test_session_past_its_time_limit_is_interrupted():
    # Regression (decision 059): an idle session used to stay active forever.
    session, p = make(plan=planned(2), max_session_seconds=0.05)
    ws = FakeSocket(START, answer("a"))  # then the client goes idle

    await session.run(ws)

    assert p["events"].events == [(7, "interrupted", "session time limit reached")]
    assert ws.sent[-1]["code"] == "session_time_limit"
    assert ws.closed[0] == 1008
    assert statuses(p) == [("answered", "a"), ("asked", None)]


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
    assert p["events"].events == []  # never became active


async def test_core_api_down_closes_1011():
    session, p = make(core=FakeCore(httpx.ConnectError("down")))
    ws = FakeSocket(START)

    await session.run(ws)

    assert ws.closed[0] == 1011
    assert p["events"].events == []


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
    session, p = make(plan=planned(1))
    ws = FakeSocket(START, {"type": "nope"}, answer("a"))

    await session.run(ws)

    assert "error" in ws.types()
    assert p["events"].events == [(7, "completed", None)]


# --- Spoken answers (decisions 043, 045) --------------------------------------


async def test_spoken_answer_is_transcribed_recorded_and_echoed():
    transcriber = FakeTranscriber("I used asyncpg")
    session, p = make(transcriber=transcriber, plan=planned(1))
    ws = FakeSocket(START, PCM, PCM, AUDIO_END)

    await session.run(ws)

    assert ws.types() == [
        "session.ready", "question.text", "question.audio_end", "transcript.final",
        "turn.complete", "session.end",
    ]
    assert ws.sent[3] == {"type": "transcript.final", "seq": 1, "text": "I used asyncpg"}
    # Frames were joined into one answer, and the question was the prompt.
    assert transcriber.calls == [(PCM + PCM, "Q1?")]
    question = p["sessions"].questions[1]
    assert question["answer"] == "I used asyncpg"
    assert "stt_ms" in question["timings"]


@pytest.mark.parametrize(
    ("first_try", "transcripts"),
    [
        ([AUDIO_END], ["real answer"]),  # no frames: STT is never called
        ([PCM, AUDIO_END], ["", "real answer"]),  # frames with no words in them
    ],
)
async def test_silence_gets_no_speech_and_the_turn_waits(first_try, transcripts):
    transcriber = FakeTranscriber(*transcripts)
    session, p = make(transcriber=transcriber, plan=planned(1))
    ws = FakeSocket(START, *first_try, PCM, AUDIO_END)

    await session.run(ws)

    errors = [m for m in ws.sent if m["type"] == "error"]
    assert [e["code"] for e in errors] == ["no_speech"]
    assert statuses(p) == [("answered", "real answer")]
    assert p["events"].events == [(7, "completed", None)]


async def test_over_long_answer_is_dropped_then_retried():
    transcriber = FakeTranscriber("short one")
    session, p = make(transcriber=transcriber, plan=planned(1), max_answer_seconds=1)
    one_second = b"\x00" * 32_000
    ws = FakeSocket(START, one_second, PCM, PCM, AUDIO_END, PCM, AUDIO_END)

    await session.run(ws)

    assert [m["code"] for m in ws.sent if m["type"] == "error"] == ["answer_too_long"]
    # Only the retry reached STT; the over-long audio was discarded.
    assert transcriber.calls == [(PCM, "Q1?")]
    assert statuses(p) == [("answered", "short one")]


async def test_stt_failure_is_interrupted():
    session, p = make(transcriber=FakeTranscriber(RuntimeError("groq 503")))
    ws = FakeSocket(START, PCM, AUDIO_END)

    await session.run(ws)

    (_, event_type, message), = p["events"].events
    assert event_type == "interrupted"
    assert "groq 503" in message
    assert ws.closed[0] == 1011


# --- Spoken questions (decision 044) ------------------------------------------


async def test_question_audio_streams_between_text_and_audio_end():
    synth = FakeSynthesizer()
    session, p = make(synthesizer=synth, plan=planned(1))
    ws = FakeSocket(START, answer("a"))

    await session.run(ws)

    assert synth.texts == ["Q1?"]
    assert ws.audio_out == [b"aud1-Q1?", b"aud2"]
    assert {"tts_first_byte_ms", "tts_ms"} <= p["sessions"].questions[1]["timings"].keys()


async def test_tts_failure_is_interrupted_with_question_on_record():
    session, p = make(synthesizer=FakeSynthesizer(fail=True))
    ws = FakeSocket(START)

    await session.run(ws)

    (_, event_type, message), = p["events"].events
    assert event_type == "interrupted"
    assert "deepgram 402" in message
    assert ws.closed[0] == 1011
    assert statuses(p)[0] == ("asked", None)
