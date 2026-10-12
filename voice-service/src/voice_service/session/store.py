"""Persistence for interview sessions: one MongoDB document per interview (decision 053).

MongoDB holds no schema, so the Pydantic models below are the schema:
whole documents and questions are built from them on write, and every
read is validated against them. Partial updates set single fields that
the models describe.

Every write is a single-document update, so it is atomic without a
transaction. `questions[i]` holds `seq` i + 1, which lets writes address a
question by position.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from voice_service.db import SESSIONS

PlanStatus = Literal["generating", "ready", "failed"]
QuestionStatus = Literal["planned", "asked", "answered"]


class PlannedQuestion(BaseModel):
    """A question as the planner writes it and the live session asks it."""

    model_config = ConfigDict(frozen=True)

    seq: int = Field(ge=1)
    area: str
    topic: str
    text: str
    chunk_ids: list[int]


class StoredQuestion(PlannedQuestion):
    """A planned question as stored, with what happened to it."""

    status: QuestionStatus = "planned"
    answer: str | None = None
    timings: dict[str, int] = {}
    asked_at: datetime | None = None
    answered_at: datetime | None = None


class PlanState(BaseModel):
    plan_status: PlanStatus
    error_message: str | None = None
    # Only meaningful when `failed`: false means retrying can't help.
    retryable: bool | None = None


class PlanJob(BaseModel):
    interview_id: int
    repository_id: int
    plan_status: PlanStatus


class SessionDocument(PlanState):
    """The whole document in `interview_sessions`. Mongo's `_id` is ignored on read."""

    interview_id: int
    repository_id: int
    plan_attempts: int = 0
    questions: list[StoredQuestion] = []
    created_at: datetime
    updated_at: datetime


class SessionStore:
    def __init__(self, db: AsyncDatabase) -> None:
        self._sessions: AsyncCollection = db[SESSIONS]

    # --- Planning (decision 052) ---------------------------------------------

    async def claim_plan(self, *, interview_id: int, repository_id: int) -> bool:
        """Mark the plan `generating` if it is new or `failed`. False: leave it alone.

        A plan that is `generating` or `ready` is never restarted, so a
        repeated trigger does nothing.
        """
        now = datetime.now(UTC)
        fresh = SessionDocument(
            interview_id=interview_id,
            repository_id=repository_id,
            plan_status="generating",
            created_at=now,
            updated_at=now,
        )
        try:
            await self._sessions.insert_one(fresh.model_dump())
            return True
        except DuplicateKeyError:
            pass
        restart = fresh.model_dump(
            include={"plan_status", "error_message", "retryable", "plan_attempts", "questions",
                     "updated_at"}
        )
        result = await self._sessions.update_one(
            {"interview_id": interview_id, "plan_status": "failed"}, {"$set": restart}
        )
        return result.modified_count == 1

    async def get_plan_job(self, interview_id: int) -> PlanJob | None:
        doc = await self._sessions.find_one(
            {"interview_id": interview_id},
            {"_id": 0, "interview_id": 1, "repository_id": 1, "plan_status": 1},
        )
        return PlanJob.model_validate(doc) if doc else None

    async def count_attempt(self, interview_id: int) -> None:
        await self._sessions.update_one(
            {"interview_id": interview_id}, {"$inc": {"plan_attempts": 1}}
        )

    async def save_plan(self, interview_id: int, questions: list[PlannedQuestion]) -> None:
        stored = [StoredQuestion(**q.model_dump()).model_dump() for q in questions]
        await self._set_if_generating(interview_id, {"plan_status": "ready", "questions": stored})

    async def fail_plan(self, interview_id: int, error_message: str, *, retryable: bool) -> None:
        state = PlanState(plan_status="failed", error_message=error_message, retryable=retryable)
        await self._set_if_generating(interview_id, state.model_dump())

    async def list_generating(self) -> list[int]:
        """Interviews whose planning was cut off by a crash or reload."""
        cursor = self._sessions.find({"plan_status": "generating"}, {"interview_id": 1})
        return [doc["interview_id"] async for doc in cursor]

    async def get_plan_state(self, interview_id: int) -> PlanState | None:
        doc = await self._sessions.find_one(
            {"interview_id": interview_id},
            {"_id": 0, "plan_status": 1, "error_message": 1, "retryable": 1},
        )
        return PlanState.model_validate(doc) if doc else None

    # --- The live session ------------------------------------------------------

    async def load_plan(self, interview_id: int) -> list[StoredQuestion] | None:
        """The planned questions in order, or None if the plan isn't `ready`."""
        return await self._questions({"interview_id": interview_id, "plan_status": "ready"})

    async def mark_asked(self, interview_id: int, seq: int) -> None:
        """Before the question is sent, so an interruption still records it (decision 008)."""
        await self._update_question(
            interview_id, seq, expected="planned",
            fields={"status": "asked", "asked_at": datetime.now(UTC)},
        )

    async def record_answer(self, interview_id: int, seq: int, answer: str) -> None:
        await self._update_question(
            interview_id, seq, expected="asked",
            fields={"status": "answered", "answer": answer, "answered_at": datetime.now(UTC)},
        )

    async def add_timings(self, interview_id: int, seq: int, timings: dict[str, int]) -> None:
        i = seq - 1
        await self._sessions.update_one(
            {"interview_id": interview_id},
            {
                "$set": {f"questions.{i}.timings.{stage}": ms for stage, ms in timings.items()},
                "$currentDate": {"updated_at": True},
            },
        )

    # --- For Evaluation Service (decision 049) --------------------------------

    async def list_turns(self, interview_id: int) -> list[dict[str, Any]]:
        """The asked questions in the `/turns` shape; empty if none.

        Timings stay internal: they measure the pipeline, not the candidate.
        """
        questions = await self._questions({"interview_id": interview_id}) or []
        return [
            {
                "seq": q.seq,
                "question_text": q.text,
                "answer_text": q.answer,
                "status": q.status,
                "retrieved_chunk_ids": q.chunk_ids,
            }
            for q in questions
            if q.status != "planned"
        ]

    # --- Helpers --------------------------------------------------------------

    async def _questions(self, query: dict[str, Any]) -> list[StoredQuestion] | None:
        doc = await self._sessions.find_one(query, {"_id": 0, "questions": 1})
        if doc is None:
            return None
        return [StoredQuestion.model_validate(q) for q in doc.get("questions", [])]

    async def _set_if_generating(self, interview_id: int, fields: dict[str, Any]) -> None:
        # Guarded so a stale job can't overwrite a plan that moved on.
        await self._sessions.update_one(
            {"interview_id": interview_id, "plan_status": "generating"},
            {"$set": fields, "$currentDate": {"updated_at": True}},
        )

    async def _update_question(
        self,
        interview_id: int,
        seq: int,
        *,
        expected: QuestionStatus,
        fields: dict[str, Any],
    ) -> None:
        # The status guard makes each step happen once; a second write is a
        # bug, and silently overwriting would hide it.
        i = seq - 1
        result = await self._sessions.update_one(
            {"interview_id": interview_id, f"questions.{i}.status": expected},
            {
                "$set": {f"questions.{i}.{name}": value for name, value in fields.items()},
                "$currentDate": {"updated_at": True},
            },
        )
        if result.modified_count != 1:
            raise RuntimeError(f"interview {interview_id} question {seq} was not '{expected}'")
