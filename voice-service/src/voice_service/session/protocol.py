"""WebSocket protocol (decisions 039, 045).

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
    # megabytes into the prompt and the turns table.
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
# Plain dicts: the server only builds these, never parses them.


def session_ready(interview_id: int) -> dict[str, Any]:
    return {"type": "session.ready", "interview_id": interview_id}


def question_text(turn_id: int, seq: int, text: str) -> dict[str, Any]:
    return {"type": "question.text", "turn_id": turn_id, "seq": seq, "text": text}


def question_audio_end(turn_id: int) -> dict[str, Any]:
    """All of the question's audio frames have been sent."""
    return {"type": "question.audio_end", "turn_id": turn_id}


def transcript_final(turn_id: int, text: str) -> dict[str, Any]:
    return {"type": "transcript.final", "turn_id": turn_id, "text": text}


def turn_complete(turn_id: int) -> dict[str, Any]:
    return {"type": "turn.complete", "turn_id": turn_id}


def session_end(reason: Literal["completed", "ended_by_client"]) -> dict[str, Any]:
    return {"type": "session.end", "reason": reason}


def error(code: str, message: str) -> dict[str, Any]:
    return {"type": "error", "code": code, "message": message}
