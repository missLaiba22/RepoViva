"""Grade one answered turn, then enforce grounding in code (decision 050)."""

from __future__ import annotations

import logging
import re

from evaluation_service.clients.repository import Chunk
from evaluation_service.clients.voice import Turn
from evaluation_service.grading.llm import JsonLlm
from evaluation_service.grading.models import TurnGrade
from evaluation_service.grading.prompts import GRADER_SYSTEM_PROMPT, build_grade_prompt

logger = logging.getLogger(__name__)

# "chunk 142", "chunks 199 and 493", "chunks 1, 2, and 3"
_CHUNK_REF = re.compile(r"\bchunks? (\d+(?:(?:,? and |, )\d+)*)", re.IGNORECASE)


def name_chunk_refs(text: str, chunks: dict[int, Chunk]) -> str:
    """Replace chunk ids in prose with file:line, which the candidate can open.

    The prompt asks for this, but the model doesn't always comply, and an
    id means nothing outside this service.
    """

    def label(i: str) -> str:
        c = chunks.get(int(i))
        return f"{c.filename}:{c.start_line}" if c else "the code"

    return _CHUNK_REF.sub(
        lambda m: " and ".join(dict.fromkeys(label(i) for i in re.findall(r"\d+", m.group(1)))),
        text,
    )


def _name_refs_in_grade(grade: TurnGrade, chunks: dict[int, Chunk]) -> TurnGrade:
    def fix(text: str) -> str:
        return name_chunk_refs(text, chunks)

    return grade.model_copy(
        update={
            "correctness": grade.correctness.model_copy(
                update={"justification": fix(grade.correctness.justification)}
            ),
            "clarity": grade.clarity.model_copy(
                update={"justification": fix(grade.clarity.justification)}
            ),
            "strengths": [fix(s) for s in grade.strengths],
            "gaps": [fix(g) for g in grade.gaps],
            "key_points": [
                kp.model_copy(update={"point": fix(kp.point)}) for kp in grade.key_points
            ],
        }
    )


def enforce_grounding(grade: TurnGrade, allowed_ids: set[int]) -> tuple[TurnGrade, int]:
    """Keep only citations of chunks the model was shown.

    A key point left with no valid citation is dropped: it may be true,
    but nothing shows it is true of this project. Returns the cleaned
    grade and how many citations were dropped, for the logs.
    """
    dropped = 0
    key_points = []
    for kp in grade.key_points:
        valid = [i for i in kp.chunk_ids if i in allowed_ids]
        dropped += len(kp.chunk_ids) - len(valid)
        if valid:
            key_points.append(kp.model_copy(update={"chunk_ids": valid}))
    evidence = [i for i in grade.evidence_chunk_ids if i in allowed_ids]
    dropped += len(grade.evidence_chunk_ids) - len(evidence)
    cleaned = grade.model_copy(update={"key_points": key_points, "evidence_chunk_ids": evidence})
    return cleaned, dropped


async def grade_turn(
    llm: JsonLlm, turn: Turn, previous: Turn | None, chunks: list[Chunk]
) -> TurnGrade | None:
    """The grounded grade, or None if the model never returned a usable one."""
    grade = await llm.complete(
        system=GRADER_SYSTEM_PROMPT,
        user=build_grade_prompt(turn, previous, chunks),
        schema=TurnGrade,
    )
    if grade is None:
        return None
    by_id = {c.id: c for c in chunks}
    grade, dropped = enforce_grounding(grade, set(by_id))
    if dropped:
        logger.info("turn %d: dropped %d ungrounded citation(s)", turn.seq, dropped)
    return _name_refs_in_grade(grade, by_id)
