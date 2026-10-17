"""WebSocket protocol (decisions 039, 045, 053).

JSON text frames, {"type": ..., ...}, carry control messages. Binary
frames carry audio and are not modelled here: client → server is PCM16
16 kHz mono answer audio, server → client is PCM16 24 kHz mono question
audio.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

# --- Client → Server ---------------------------------------------------------


class SessionStart(BaseModel):
    type: Literal["session.start"]
    # Same cap as Core API's consume body (decision 035).
    token: str = Field(min_length=1, max_length=128)


class AudioEnd(BaseModel):
    """The binary frames since the last answer form one answer: transcribe."""

    type: Literal["audio.end"]


class AnswerText(BaseModel):
    """Typed answer: the development/accessibility fallback (decision 045)."""

    type: Literal["answer.text"]
    # Generous for a spoken-length answer; stops a client pushing
    # megabytes into the session document.
    text: str = Field(min_length=1, max_length=5000)


class SessionEnd(BaseModel):
    type: Literal["session.end"]


ClientMessage = Annotated[
    SessionStart | AudioEnd | AnswerText | SessionEnd, Field(discriminator="type")
]
_client_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


def parse_client_message(raw: str) -> ClientMessage:
    """Raises pydantic.ValidationError for anything not in the protocol."""
    return _client_adapter.validate_json(raw)


# --- Server → Client ---------------------------------------------------------
# Plain dicts: the server only builds these, never parses them. A question
# is identified by its `seq` in the plan (decision 053).


def session_ready(interview_id: int, question_count: int) -> dict[str, Any]:
    # question_count: the plan's length, for "Question N of M" (decision 062).
    return {"type": "session.ready", "interview_id": interview_id, "question_count": question_count}


def question_text(seq: int, text: str) -> dict[str, Any]:
    return {"type": "question.text", "seq": seq, "text": text}


def question_audio_end(seq: int) -> dict[str, Any]:
    """All of the question's audio frames have been sent."""
    return {"type": "question.audio_end", "seq": seq}


def transcript_final(seq: int, text: str) -> dict[str, Any]:
    return {"type": "transcript.final", "seq": seq, "text": text}


def turn_complete(seq: int) -> dict[str, Any]:
    return {"type": "turn.complete", "seq": seq}


def session_end(reason: Literal["completed", "ended_by_client"]) -> dict[str, Any]:
    return {"type": "session.end", "reason": reason}


def error(code: str, message: str) -> dict[str, Any]:
    return {"type": "error", "code": code, "message": message}
