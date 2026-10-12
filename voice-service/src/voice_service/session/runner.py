"""The interview loop for one WebSocket connection (decisions 035–036, 039–045, 052).

    session.start ─▶ consume token ─▶ load plan ─▶ [persist ─▶ ask (text + TTS audio)
                       ◀── audio frames ─ audio.end ─▶ STT ─▶ persist] × planned questions
                    ─▶ end event

The questions were written before the session (decision 052), so a turn
makes no LLM call and no retrieval.

Collaborators are injected so tests can run the whole loop with fakes:
no network, no database.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx
from fastapi import WebSocketDisconnect
from pydantic import ValidationError

from voice_service.clients.core_api import ConsumedSession, TokenRejectedError
from voice_service.session import protocol
from voice_service.session.protocol import AnswerText, AudioEnd, SessionEnd, SessionStart
from voice_service.session.store import PlannedQuestion
from voice_service.speech.stt import BYTES_PER_SECOND

logger = logging.getLogger(__name__)

# RFC 6455 close codes.
_CLOSE_NORMAL = 1000
_CLOSE_POLICY_VIOLATION = 1008  # bad/missing/rejected token (decision 035)
_CLOSE_INTERNAL_ERROR = 1011

# The single message a client sees for any admission failure (decision 035).
_GENERIC_ADMISSION_FAILURE = "session could not be started"

Outcome = Literal["completed", "ended_by_client"]


# --- Collaborator interfaces --------------------------------------------------


class Channel(Protocol):
    """The subset of fastapi.WebSocket the runner uses.

    `receive()` returns the raw ASGI message rather than `receive_text()`,
    because a client frame may be text (JSON control messages) or binary
    (audio, decision 045), and only the message says which.
    """

    async def receive(self) -> dict: ...
    async def send_json(self, data: dict) -> None: ...
    async def send_bytes(self, data: bytes) -> None: ...
    async def close(self, code: int = 1000, reason: str | None = None) -> None: ...


class CoreApi(Protocol):
    async def consume_token(self, token: str) -> ConsumedSession: ...
    async def send_interview_event(
        self, interview_id: int, event_type: str, *, error_message: str | None = None
    ) -> None: ...


class Transcriber(Protocol):
    async def transcribe(self, pcm: bytes, *, prompt: str) -> str: ...


class Synthesizer(Protocol):
    def synthesize(self, text: str) -> AsyncIterator[bytes]: ...


class Sessions(Protocol):
    async def load_plan(self, interview_id: int) -> Sequence[PlannedQuestion] | None: ...
    async def mark_asked(self, interview_id: int, seq: int) -> None: ...
    async def record_answer(self, interview_id: int, seq: int, answer: str) -> None: ...
    async def add_timings(self, interview_id: int, seq: int, timings: dict[str, int]) -> None: ...


@dataclass(frozen=True)
class SessionConfig:
    session_start_timeout_s: float
    max_answer_seconds: int = 180  # decision 043


class _PlanNotReadyError(Exception):
    """The live page opens the socket only once the plan is ready (decision 052)."""


@dataclass(frozen=True)
class _Answer:
    text: str
    stt_ms: int | None  # None: typed (answer.text), no transcription


# --- Runner -------------------------------------------------------------------


class InterviewSession:
    def __init__(
        self,
        *,
        core_api: CoreApi,
        transcriber: Transcriber,
        synthesizer: Synthesizer,
        sessions: Sessions,
        config: SessionConfig,
    ) -> None:
        self._core = core_api
        self._transcriber = transcriber
        self._synthesizer = synthesizer
        self._sessions = sessions
        self._config = config

    async def run(self, ws: Channel) -> None:
        """Drive one connection from admission to its end event.

        Assumes the socket is already accepted.
        """
        session = await self._admit(ws)
        if session is None:
            return  # never became active: no end event to send

        # From here the interview is `active` in Core API, so every exit
        # path below must report how it ended (decision 041).
        try:
            plan = await self._sessions.load_plan(session.interview_id)
            if plan is None:
                raise _PlanNotReadyError
            await ws.send_json(protocol.session_ready(session.interview_id))
            outcome = await self._interview(ws, session.interview_id, plan)
        except _PlanNotReadyError:
            # Only the token tells us the interview, so this check can only
            # come after the consume (decision 052).
            logger.warning(
                "interview %s: session started before its plan was ready", session.interview_id
            )
            await self._core.send_interview_event(
                session.interview_id, "interview.interrupted", error_message="plan not ready",
            )
            await _safe_send(ws, protocol.error("plan_not_ready", "the interview isn't ready yet"))
            await _safe_close(ws, _CLOSE_POLICY_VIOLATION)
            return
        except WebSocketDisconnect:
            logger.info("interview %s: client disconnected", session.interview_id)
            await self._core.send_interview_event(
                session.interview_id, "interview.interrupted",
                error_message="client disconnected",
            )
            return
        except Exception as exc:
            logger.exception("interview %s failed", session.interview_id)
            await self._core.send_interview_event(
                session.interview_id, "interview.interrupted",
                error_message=f"{type(exc).__name__}: {exc}",
            )
            await _safe_send(ws, protocol.error("internal_error", "the interview hit an error"))
            await _safe_close(ws, _CLOSE_INTERNAL_ERROR)
            return

        await self._core.send_interview_event(session.interview_id, "interview.completed")
        await _safe_send(ws, protocol.session_end(outcome))
        await _safe_close(ws, _CLOSE_NORMAL)

    async def _admit(self, ws: Channel) -> ConsumedSession | None:
        """Wait for session.start and consume its token. None = closed."""
        try:
            raw = await asyncio.wait_for(_receive(ws), self._config.session_start_timeout_s)
        except TimeoutError:
            logger.info("closing socket: no session.start within timeout")
            await _safe_close(ws, _CLOSE_POLICY_VIOLATION, _GENERIC_ADMISSION_FAILURE)
            return None
        except WebSocketDisconnect:
            return None

        msg = None
        if isinstance(raw, str):  # a binary first frame is never session.start
            with contextlib.suppress(ValidationError):
                msg = protocol.parse_client_message(raw)
        if not isinstance(msg, SessionStart):
            logger.info("closing socket: first message was not a valid session.start")
            await _safe_close(ws, _CLOSE_POLICY_VIOLATION, _GENERIC_ADMISSION_FAILURE)
            return None

        try:
            return await self._core.consume_token(msg.token)
        except TokenRejectedError as exc:
            # The reason stays in our logs; the client gets the generic
            # close (decision 035). `consumed` is the replay signal.
            logger.warning("session token rejected: reason=%s", exc.reason)
            await _safe_close(ws, _CLOSE_POLICY_VIOLATION, _GENERIC_ADMISSION_FAILURE)
            return None
        except httpx.HTTPError:
            logger.exception("could not reach Core API to consume session token")
            await _safe_close(ws, _CLOSE_INTERNAL_ERROR, _GENERIC_ADMISSION_FAILURE)
            return None

    async def _interview(
        self, ws: Channel, interview_id: int, plan: Sequence[PlannedQuestion]
    ) -> Outcome:
        for question in plan:
            seq = question.seq
            # 1. Persist before sending, so an interruption still records it.
            await self._sessions.mark_asked(interview_id, seq)

            # 2. Ask: the text first (captions), then the spoken question.
            await ws.send_json(protocol.question_text(seq, question.text))
            tts_timings = await self._speak(ws, seq, question.text)
            await self._sessions.add_timings(interview_id, seq, tts_timings)
            logger.info(
                "interview %s question %s: tts_first_byte=%sms tts=%sms",
                interview_id, seq, tts_timings["tts_first_byte_ms"], tts_timings["tts_ms"],
            )

            # 3. Wait for the answer (or the client ending the session).
            reply = await self._await_answer(ws, question.text)
            if isinstance(reply, SessionEnd):
                return "ended_by_client"

            if reply.stt_ms is not None:
                # Show what we heard, so a misheard answer is visible.
                await ws.send_json(protocol.transcript_final(seq, reply.text))
            await self._sessions.record_answer(interview_id, seq, reply.text)
            if reply.stt_ms is not None:
                await self._sessions.add_timings(interview_id, seq, {"stt_ms": reply.stt_ms})
                logger.info("interview %s question %s: stt=%sms", interview_id, seq, reply.stt_ms)
            await ws.send_json(protocol.turn_complete(seq))

        return "completed"

    async def _speak(self, ws: Channel, seq: int, question: str) -> dict[str, int]:
        """Stream the question's audio to the client as binary frames.

        Each chunk is forwarded the moment it arrives, so playback starts
        before synthesis ends. `send_bytes` waits while the socket's send
        buffer is full, which paces us to the client's network speed
        (backpressure) instead of piling audio up in memory.
        """
        t0 = time.perf_counter()
        first_byte: float | None = None
        async for chunk in self._synthesizer.synthesize(question):
            if first_byte is None:
                first_byte = time.perf_counter()
            await ws.send_bytes(chunk)
        end = time.perf_counter()
        await ws.send_json(protocol.question_audio_end(seq))
        return {"tts_first_byte_ms": _ms(t0, first_byte or end), "tts_ms": _ms(t0, end)}

    async def _await_answer(self, ws: Channel, question: str) -> _Answer | SessionEnd:
        """The next answer, spoken or typed, or session.end.

        Spoken: binary frames accumulate until audio.end, then one STT call
        (decision 043). Problems the client can fix — a protocol mistake,
        silence, an over-long answer — get an `error` and the same turn
        keeps waiting.
        """
        max_bytes = self._config.max_answer_seconds * BYTES_PER_SECOND
        audio = bytearray()
        discarding = False  # over the cap: drop frames until this answer's audio.end

        while True:
            raw = await _receive(ws)

            if isinstance(raw, bytes):
                if discarding:
                    continue
                audio.extend(raw)
                if len(audio) > max_bytes:
                    audio.clear()
                    discarding = True
                    await ws.send_json(protocol.error(
                        "answer_too_long",
                        f"answers are limited to {self._config.max_answer_seconds} seconds",
                    ))
                continue

            try:
                msg = protocol.parse_client_message(raw)
            except ValidationError:
                await ws.send_json(protocol.error("bad_message", "expected an answer or session.end"))
                continue

            if isinstance(msg, AudioEnd):
                if discarding:  # the client was already told; start afresh
                    discarding = False
                    continue
                transcript, stt_ms = await self._transcribe(bytes(audio), question)
                audio.clear()  # decision 009: audio is not kept past transcription
                if not transcript:
                    await ws.send_json(protocol.error("no_speech", "no speech heard, please answer again"))
                    continue
                return _Answer(transcript, stt_ms)
            if isinstance(msg, AnswerText):
                return _Answer(msg.text, None)
            if isinstance(msg, SessionEnd):
                return msg
            await ws.send_json(protocol.error("bad_message", "session already started"))

    async def _transcribe(self, pcm: bytes, question: str) -> tuple[str, int]:
        if not pcm:
            return "", 0  # nothing to send; don't spend a request on it
        t0 = time.perf_counter()
        text = await self._transcriber.transcribe(pcm, prompt=question)
        return text, _ms(t0, time.perf_counter())


async def _receive(ws: Channel) -> str | bytes:
    """Next client frame: text or binary.

    A raw ASGI disconnect is a message, not an exception, so raise it the
    way `receive_text()` would; the runner's handlers stay unchanged.
    """
    message = await ws.receive()
    if message["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(message.get("code", 1000))
    if message.get("text") is not None:
        return message["text"]
    return message.get("bytes") or b""


def _ms(start: float, end: float) -> int:
    return round((end - start) * 1000)


async def _safe_send(ws: Channel, data: dict) -> None:
    """Send if the socket is still open; at the end of a session, failure is fine."""
    # A disconnect surfaces as several exception types depending on timing.
    with contextlib.suppress(Exception):
        await ws.send_json(data)


async def _safe_close(ws: Channel, code: int, reason: str | None = None) -> None:
    # Already closed by the client is fine.
    with contextlib.suppress(Exception):
        await ws.close(code=code, reason=reason)
