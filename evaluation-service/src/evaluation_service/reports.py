"""Persistence for `reports` (decisions 049, 050).

The row's status is the only coordination between a trigger, the
background generation and a startup resume, so every transition is a
single conditional statement:

    (none)  ──claim──▶ generating ──mark_ready──▶ ready
    failed  ──claim──▶ generating ──mark_failed─▶ failed
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import asyncpg

from evaluation_service.pipeline import ReportContent

# Inserts a new row, or restarts a failed one. A row that is `generating`
# or `ready` matches neither branch, so nothing is returned and the
# trigger is a no-op (decision 049). One statement, so two triggers
# racing for the same interview can't both win.
_CLAIM = """
    INSERT INTO reports (interview_id, repository_id, partial)
    VALUES ($1, $2, $3)
    ON CONFLICT (interview_id) DO UPDATE
    SET status = 'generating',
        repository_id = EXCLUDED.repository_id,
        partial = EXCLUDED.partial,
        model = NULL,
        prompt_version = NULL,
        summary = NULL,
        turn_evaluations = NULL,
        error_message = NULL,
        created_at = now(),
        completed_at = NULL
    WHERE reports.status = 'failed'
    RETURNING id
"""

_GET_STATUS = "SELECT status FROM reports WHERE interview_id = $1"

_GET = """
    SELECT interview_id, status, partial, model, prompt_version, summary,
           turn_evaluations, error_message, created_at, completed_at
    FROM reports
    WHERE interview_id = $1
"""

# `status = 'generating'` guard on both finishes: a result only lands on
# the run that claimed the row, never on top of a newer outcome.
_MARK_READY = """
    UPDATE reports
    SET status = 'ready', model = $2, prompt_version = $3,
        summary = $4::jsonb, turn_evaluations = $5::jsonb, completed_at = now()
    WHERE interview_id = $1 AND status = 'generating'
"""

_MARK_FAILED = """
    UPDATE reports
    SET status = 'failed', error_message = $2, completed_at = now()
    WHERE interview_id = $1 AND status = 'generating'
"""

# Oldest first, so a resume finishes reports in the order they were asked for.
_LIST_GENERATING = """
    SELECT interview_id, repository_id, partial
    FROM reports
    WHERE status = 'generating'
    ORDER BY created_at
"""


@dataclass(frozen=True)
class PendingReport:
    interview_id: int
    repository_id: int
    partial: bool


class ReportStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def claim(self, *, interview_id: int, repository_id: int, partial: bool) -> bool:
        """Mark the report `generating`. True if the caller should now generate it."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval(_CLAIM, interview_id, repository_id, partial) is not None

    async def get_status(self, interview_id: int) -> str | None:
        async with self._pool.acquire() as conn:
            return await conn.fetchval(_GET_STATUS, interview_id)

    async def get(self, interview_id: int) -> dict | None:
        """The report as JSON-ready data, or None if there is no row."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(_GET, interview_id)
        if row is None:
            return None
        report = dict(row)
        # asyncpg returns JSONB as text unless a codec is registered.
        for key in ("summary", "turn_evaluations"):
            if report[key] is not None:
                report[key] = json.loads(report[key])
        for key in ("created_at", "completed_at"):
            if report[key] is not None:
                report[key] = report[key].isoformat()
        return report

    async def mark_ready(self, interview_id: int, content: ReportContent) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                _MARK_READY,
                interview_id,
                content.model,
                content.prompt_version,
                json.dumps(content.summary),
                json.dumps(content.turn_evaluations),
            )

    async def mark_failed(self, interview_id: int, error_message: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(_MARK_FAILED, interview_id, error_message)

    async def list_generating(self) -> list[PendingReport]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(_LIST_GENERATING)
        return [
            PendingReport(r["interview_id"], r["repository_id"], r["partial"]) for r in rows
        ]
