"""What the grading model must return (decision 050), validated with pydantic.

Lists the model over-fills are trimmed rather than rejected: an extra
strength isn't worth a retry, while a missing or out-of-range score is.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

MAX_KEY_POINTS = 4
MAX_FEEDBACK_ITEMS = 3
MAX_FILES = 5


def _trim(items: list, limit: int) -> list:
    return items[:limit]


class Score(BaseModel):
    score: int = Field(ge=1, le=5)
    justification: str = Field(min_length=1)


class KeyPoint(BaseModel):
    point: str = Field(min_length=1)
    chunk_ids: list[int] = []


class TurnGrade(BaseModel):
    correctness: Score
    clarity: Score
    strengths: list[str] = []
    gaps: list[str] = []
    key_points: list[KeyPoint] = []
    evidence_chunk_ids: list[int] = []

    @field_validator("strengths", "gaps")
    @classmethod
    def _trim_feedback(cls, v: list[str]) -> list[str]:
        return _trim(v, MAX_FEEDBACK_ITEMS)

    @field_validator("key_points")
    @classmethod
    def _trim_key_points(cls, v: list[KeyPoint]) -> list[KeyPoint]:
        return _trim(v, MAX_KEY_POINTS)


class FileNote(BaseModel):
    file: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class SummaryNotes(BaseModel):
    strengths: list[str] = []
    improvements: list[str] = []
    files_to_revisit: list[FileNote] = []

    @field_validator("strengths", "improvements")
    @classmethod
    def _trim_feedback(cls, v: list[str]) -> list[str]:
        return _trim(v, MAX_FEEDBACK_ITEMS)

    @field_validator("files_to_revisit")
    @classmethod
    def _trim_files(cls, v: list[FileNote]) -> list[FileNote]:
        return _trim(v, MAX_FILES)
