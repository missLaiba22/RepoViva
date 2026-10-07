"""The report summary: numbers computed in code, notes written by the LLM (decision 050)."""

from __future__ import annotations

import logging

from evaluation_service.grading.llm import JsonLlm
from evaluation_service.grading.models import SummaryNotes
from evaluation_service.grading.prompts import SUMMARY_SYSTEM_PROMPT, build_summary_prompt

logger = logging.getLogger(__name__)


def _average(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def compute_scores(turn_evaluations: list[dict]) -> dict:
    """Averages over graded turns only; unanswered and ungraded turns don't count."""
    graded = [e for e in turn_evaluations if e["status"] == "graded"]
    return {
        "average_correctness": _average([e["correctness"]["score"] for e in graded]),
        "average_clarity": _average([e["clarity"]["score"] for e in graded]),
        "turns_asked": len(turn_evaluations),
        "turns_answered": sum(1 for e in turn_evaluations if e["status"] != "not_answered"),
        "turns_graded": len(graded),
    }


async def write_notes(llm: JsonLlm, turn_evaluations: list[dict]) -> SummaryNotes | None:
    """Strengths, improvements and files to revisit; None if nothing was graded
    or the model never returned a usable reply.

    Files are kept only if they back one of the graded turns, so the list
    can't point at code the candidate was never asked about.
    """
    graded = [e for e in turn_evaluations if e["status"] == "graded"]
    if not graded:
        return None
    notes = await llm.complete(
        system=SUMMARY_SYSTEM_PROMPT, user=build_summary_prompt(graded), schema=SummaryNotes
    )
    if notes is None:
        return None
    known = {s["filename"] for e in graded for s in e["sources"]}
    kept = [f for f in notes.files_to_revisit if f.file in known]
    if len(kept) < len(notes.files_to_revisit):
        logger.info("summary: dropped %d unknown file(s)", len(notes.files_to_revisit) - len(kept))
    return notes.model_copy(update={"files_to_revisit": kept})
