"""Persistence for `turns` (decision 040)."""

from __future__ import annotations

import json

import asyncpg

_INSERT_TURN = """
    INSERT INTO turns (interview_id, seq, question_text, retrieved_chunk_ids, timings)
    VALUES ($1, $2, $3, $4::bigint[], $5::jsonb)
    RETURNING id
"""

# `status = 'asked'` guard: an answer is recorded once; a stray second
# write is a bug, and silently overwriting would hide it.
_RECORD_ANSWER = """
    UPDATE turns
    SET answer_text = $2, status = 'answered', answered_at = now()
    WHERE id = $1 AND status = 'asked'
"""


class TurnStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create_turn(
        self,
        *,
        interview_id: int,
        seq: int,
        question_text: str,
        retrieved_chunk_ids: list[int],
        timings: dict[str, int],
    ) -> int:
        """Insert a turn in `asked` state; returns its id."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                _INSERT_TURN,
                interview_id,
                seq,
                question_text,
                retrieved_chunk_ids,
                json.dumps(timings),
            )

    async def record_answer(self, turn_id: int, answer_text: str) -> None:
        async with self._pool.acquire() as conn:
            result = await conn.execute(_RECORD_ANSWER, turn_id, answer_text)
        if result != "UPDATE 1":
            raise RuntimeError(f"turn {turn_id} was not in 'asked' state")
