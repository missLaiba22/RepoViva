"""The interview loop for one WebSocket connection (decisions 034–036, 039–042).

    session.start ─▶ consume token ─▶ [retrieve ─▶ LLM ─▶ persist ─▶ ask
                                        ◀── answer.text ── persist] × N ─▶ end event

Collaborators are injected so tests can run the whole loop with fakes:
no network, no database, no LLM.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx
from fastapi import WebSocketDisconnect
from pydantic import ValidationError

from voice_service.clients.core_api import ConsumedSession, TokenRejectedError
from voice_service.clients.repository import Chunk
from voice_service.llm.prompts import OPENING_SEED_QUERY, Exchange
from voice_service.session import protocol
from voice_service.session.protocol import AnswerText, SessionEnd, SessionStart

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


class Retriever(Protocol):
    async def retrieve(
        self, repository_id: int, query: str, *, top_k: int, exclude_chunk_ids: list[int]
    ) -> list[Chunk]: ...


class Generator(Protocol):
    async def generate_question(self, history: list[Exchange], chunks: list[Chunk]) -> str: ...


class Turns(Protocol):
    async def create_turn(
        self,
        *,
        interview_id: int,
        seq: int,
        question_text: str,
        retrieved_chunk_ids: list[int],
        timings: dict[str, int],
    ) -> int: ...
    async def record_answer(self, turn_id: int, answer_text: str) -> None: ...


@dataclass(frozen=True)
class SessionConfig:
    max_questions: int
    session_start_timeout_s: float
    retrieval_top_k: int


# --- Runner -------------------------------------------------------------------


class InterviewSession:
    def __init__(
        self,
        *,
        core_api: CoreApi,
        retriever: Retriever,
        generator: Generator,
        turns: Turns,
        config: SessionConfig,
    ) -> None:
        self._core = core_api
        self._retriever = retriever
        self._generator = generator
        self._turns = turns
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
        await ws.send_json(protocol.session_ready(session.interview_id))
        try:
            outcome = await self._interview(ws, session)
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

    async def _interview(self, ws: Channel, session: ConsumedSession) -> Outcome:
        history: list[Exchange] = []
        used_chunk_ids: list[int] = []
        query = OPENING_SEED_QUERY  # decision 042

        for seq in range(1, self._config.max_questions + 1):
            # 1. Retrieve fresh context, steering away from code already used.
            t0 = time.perf_counter()
            chunks = await self._retriever.retrieve(
                session.repository_id, query,
                top_k=self._config.retrieval_top_k,
                exclude_chunk_ids=used_chunk_ids,
            )
            t1 = time.perf_counter()
            if not chunks:
                logger.warning(
                    "interview %s turn %s: retrieval returned no chunks",
                    session.interview_id, seq,
                )

            # 2. Generate the question.
            question = await self._generator.generate_question(history, chunks)
            t2 = time.perf_counter()

            # 3. Persist before sending, so an interruption still records it.
            chunk_ids = [c.id for c in chunks]
            timings = {"retrieval_ms": _ms(t0, t1), "llm_ms": _ms(t1, t2)}
            turn_id = await self._turns.create_turn(
                interview_id=session.interview_id,
                seq=seq,
                question_text=question,
                retrieved_chunk_ids=chunk_ids,
                timings=timings,
            )
            used_chunk_ids.extend(chunk_ids)
            # Per-stage timing log (decision 034's consequence).
            logger.info(
                "interview %s turn %s: retrieval=%sms llm=%sms chunks=%s",
                session.interview_id, seq, timings["retrieval_ms"], timings["llm_ms"],
                len(chunk_ids),
            )

            await ws.send_json(protocol.question_text(turn_id, seq, question))

            # 4. Wait for the answer (or the client ending the session).
            reply = await self._await_answer(ws)
            if isinstance(reply, SessionEnd):
                return "ended_by_client"

            await self._turns.record_answer(turn_id, reply.text)
            await ws.send_json(protocol.turn_complete(turn_id))

            history.append(Exchange(question=question, answer=reply.text))
            query = f"{question}\n{reply.text}"  # decision 042

        return "completed"

    async def _await_answer(self, ws: Channel) -> AnswerText | SessionEnd:
        """Next answer.text or session.end; protocol mistakes get an error and a retry."""
        while True:
            raw = await _receive(ws)
            if isinstance(raw, bytes):
                await ws.send_json(protocol.error("bad_message", "expected answer.text or session.end"))
                continue
            try:
                msg = protocol.parse_client_message(raw)
            except ValidationError:
                await ws.send_json(protocol.error("bad_message", "expected answer.text or session.end"))
                continue
            if isinstance(msg, (AnswerText, SessionEnd)):
                return msg
            await ws.send_json(protocol.error("bad_message", "session already started"))


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
