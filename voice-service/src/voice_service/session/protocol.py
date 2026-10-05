"""WebSocket protocol v1 (decision 039). JSON text frames: {"type": ..., ...}."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

# --- Client → Server ---------------------------------------------------------


class SessionStart(BaseModel):
    type: Literal["session.start"]
    # Same cap as Core API's consume body (decision 035).
    token: str = Field(min_length=1, max_length=128)


class AnswerText(BaseModel):
    """Text stand-in for audio.chunk / audio.end until STT lands."""

    type: Literal["answer.text"]
    # Generous for a spoken-length answer; stops a client pushing
    # megabytes into the prompt and the turns table.
    text: str = Field(min_length=1, max_length=5000)


class SessionEnd(BaseModel):
    type: Literal["session.end"]


ClientMessage = Annotated[SessionStart | AnswerText | SessionEnd, Field(discriminator="type")]
_client_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


def parse_client_message(raw: str) -> ClientMessage:
    """Raises pydantic.ValidationError for anything not in protocol v1."""
    return _client_adapter.validate_json(raw)


# --- Server → Client ---------------------------------------------------------
# Plain dicts: the server only builds these, never parses them.


def session_ready(interview_id: int) -> dict[str, Any]:
    return {"type": "session.ready", "interview_id": interview_id}


def question_text(turn_id: int, seq: int, text: str) -> dict[str, Any]:
    return {"type": "question.text", "turn_id": turn_id, "seq": seq, "text": text}


def turn_complete(turn_id: int) -> dict[str, Any]:
    return {"type": "turn.complete", "turn_id": turn_id}


def session_end(reason: Literal["completed", "ended_by_client"]) -> dict[str, Any]:
    return {"type": "session.end", "reason": reason}


def error(code: str, message: str) -> dict[str, Any]:
    return {"type": "error", "code": code, "message": message}
