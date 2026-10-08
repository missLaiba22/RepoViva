"""Build one interview's report: fetch → grade each turn → summarise (decisions 049, 050).

Pure orchestration: the clients and the LLM are passed in, so tests run
it with fakes. Persisting the result and the report's status belong to
the caller (generation.py, reports.py).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol

from evaluation_service.clients.repository import Chunk
from evaluation_service.clients.voice import Turn
from evaluation_service.grading.grader import grade_turn
from evaluation_service.grading.llm import JsonLlm
from evaluation_service.grading.prompts import PROMPT_VERSION
from evaluation_service.grading.summary import compute_scores, write_notes

logger = logging.getLogger(__name__)


class TurnSource(Protocol):
    async def get_turns(self, interview_id: int) -> list[Turn]: ...


class ChunkSource(Protocol):
    async def get_chunks(self, repository_id: int, ids: list[int]) -> dict[int, Chunk]: ...


@dataclass(frozen=True)
class ReportContent:
    partial: bool
    summary: dict
    turn_evaluations: list[dict]
    model: str
    prompt_version: str


def _source(chunk: Chunk) -> dict:
    """A reference to a chunk, small enough to store in every report.

    The code itself stays in Repository Service.
    """
    return {
        "chunk_id": chunk.id,
        "filename": chunk.filename,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
    }


def _is_answered(turn: Turn) -> bool:
    return turn.status == "answered" and bool((turn.answer_text or "").strip())


async def _evaluate_turn(
    llm: JsonLlm, turn: Turn, previous: Turn | None, chunks: dict[int, Chunk]
) -> dict:
    base = {"seq": turn.seq, "question": turn.question_text, "answer": turn.answer_text}
    if not _is_answered(turn):
        return {**base, "answer": None, "status": "not_answered"}

    # Chunks can be missing if the repository was re-ingested since the
    # interview; grading goes ahead with what's left.
    turn_chunks = [chunks[i] for i in turn.retrieved_chunk_ids if i in chunks]
    sources = [_source(c) for c in turn_chunks]
    by_id = {c.id: c for c in turn_chunks}

    started = time.monotonic()
    grade = await grade_turn(llm, turn, previous, turn_chunks)
    logger.info("turn %d graded in %.1f s", turn.seq, time.monotonic() - started)
    if grade is None:
        return {**base, "status": "not_graded", "sources": sources}

    return {
        **base,
        "status": "graded",
        "correctness": grade.correctness.model_dump(),
        "clarity": grade.clarity.model_dump(),
        "strengths": grade.strengths,
        "gaps": grade.gaps,
        "key_points": [
            {"point": kp.point, "sources": [_source(by_id[i]) for i in kp.chunk_ids]}
            for kp in grade.key_points
        ],
        "evidence": [_source(by_id[i]) for i in grade.evidence_chunk_ids],
        "sources": sources,
    }


async def generate_report(
    *,
    interview_id: int,
    repository_id: int,
    partial: bool,
    voice: TurnSource,
    repository: ChunkSource,
    llm: JsonLlm,
) -> ReportContent:
    """The report's content. Raises if Voice, Repository or the LLM provider
    fails; an unusable model reply only marks that turn `not_graded`.
    """
    tokens_before = llm.total_tokens
    turns = await voice.get_turns(interview_id)

    # One fetch for every chunk any answered turn was built from.
    ids = sorted({i for t in turns if _is_answered(t) for i in t.retrieved_chunk_ids})
    chunks = await repository.get_chunks(repository_id, ids) if ids else {}
    if len(chunks) < len(ids):
        logger.warning(
            "interview %d: %d of %d chunks no longer exist", interview_id, len(ids) - len(chunks), len(ids)
        )

    # One call at a time: the free tier's per-minute token budget is the
    # bottleneck, and parallel calls would only collide on it (decision 051).
    evaluations = []
    previous: Turn | None = None
    for turn in turns:
        evaluations.append(await _evaluate_turn(llm, turn, previous, chunks))
        previous = turn

    notes = await write_notes(llm, evaluations)
    summary = {
        **compute_scores(evaluations),
        "strengths": notes.strengths if notes else [],
        "improvements": notes.improvements if notes else [],
        "files_to_revisit": [f.model_dump() for f in notes.files_to_revisit] if notes else [],
    }
    logger.info(
        "interview %d: report used %d tokens", interview_id, llm.total_tokens - tokens_before
    )
    return ReportContent(
        partial=partial,
        summary=summary,
        turn_evaluations=evaluations,
        model=llm.model,
        prompt_version=PROMPT_VERSION,
    )
