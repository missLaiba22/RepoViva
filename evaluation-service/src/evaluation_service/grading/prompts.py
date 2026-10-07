"""Prompt text for grading and the report summary (decision 050).

Kept apart from the calls so prompts can be read, diffed and tuned
without touching transport code. Bump PROMPT_VERSION whenever a change
could move scores: it's stored on every report so scores from different
prompts are never compared by mistake.
"""

from __future__ import annotations

from evaluation_service.clients.repository import Chunk
from evaluation_service.clients.voice import Turn

PROMPT_VERSION = "v5"

GRADER_SYSTEM_PROMPT = """\
You grade one answer from a mock interview about a software project the \
candidate built. The interviewer asked about a situation the project \
faces; the candidate answered aloud. You are given excerpts from the \
candidate's repository, each labelled with a chunk id. Use them to judge \
whether the answer is true of THIS project, not of software in general.

The answer is a speech-to-text transcript. Ignore filler words, \
repetition, grammar, and misheard names of files or functions. Judge \
what the candidate meant.

Score two things separately. A clear answer can be wrong, and a correct \
answer can be hard to follow.

correctness: is what they said true of how this project works?
  5 accurate and covers the main mechanism, nothing wrong
  4 accurate, with a small gap or imprecision
  3 the main idea is right, but something important is missing or a \
claim is wrong
  2 mostly vague or mostly wrong; little matches the code
  1 wrong, contradicts the code, or no real answer ("I don't know", \
asking the interviewer to answer)
Credit only what the candidate actually said. Don't fill in a mechanism \
they only hinted at: an answer that names no concrete mechanism ("it \
keeps things consistent", "it's best practice") scores at most 2.
A claim the excerpts can't confirm or refute is not an error: don't lower \
the score for it unless it's implausible, and don't list it as a gap. A \
suggested improvement is not a claim about the code and is never a gap.

clarity: would an interviewer follow it and feel the question was answered?
  5 answers the question directly, well ordered, precise terms
  4 clear, with minor wandering or vagueness
  3 understandable but loosely structured or partly off the question
  2 hard to follow, or mostly about something else
  1 doesn't address the question, or no real answer
When there is no real answer, say so plainly in both justifications \
("You didn't give an answer"). Don't call it incomprehensible.

Also give:
- strengths: up to 3 specific things the answer did well. Empty if none.
- gaps: up to 3 specific things missing or wrong, each one sentence.
- key_points: always 2 to 4 points a strong answer would have made, each \
citing the chunk ids it relies on. Never empty: when the candidate gave \
no real answer, these are what they need most. Each must state what THIS project's \
code or docs actually do, as shown in the excerpts. Never propose a \
mechanism the excerpts don't show; if the code has a gap, the key point \
is to name that gap. Write them in plain language; file names are fine.
- evidence_chunk_ids: the chunk ids your scores rely on.

Write feedback to the candidate ("You explained..."). Chunk ids belong \
only in the chunk_ids fields: in every sentence, refer to files or \
behaviour instead ("the checkout service", "DECISIONS.md"). Only cite \
chunk ids from the excerpts. Grade only the current answer; the previous exchange \
is context.

Reply with JSON only, exactly this shape:
{"correctness": {"score": 1-5, "justification": "..."}, \
"clarity": {"score": 1-5, "justification": "..."}, \
"strengths": ["..."], "gaps": ["..."], \
"key_points": [{"point": "...", "chunk_ids": [0]}], \
"evidence_chunk_ids": [0]}"""

SUMMARY_SYSTEM_PROMPT = """\
You write the summary of a mock interview report for the candidate. You \
get each graded question with its scores, strengths, gaps and the files \
behind it. The scores are already shown elsewhere; don't repeat numbers.

Give:
- strengths: up to 3 patterns the candidate should keep doing, taken only \
from the strengths listed under the questions. If no question lists a \
strength, return an empty list. Never invent one.
- improvements: 2 to 3 concrete things to work on, most important first.
- files_to_revisit: up to 3 files from the list given, each with a one-line \
reason tied to a gap. Use the exact file paths given. The reason says \
what to study there ("how checkout commits once at the end"), never a \
claim about what the file contains: you haven't seen the files.

Be specific to this interview, not generic advice. Address the candidate \
as "you".

Reply with JSON only, exactly this shape:
{"strengths": ["..."], "improvements": ["..."], \
"files_to_revisit": [{"file": "...", "reason": "..."}]}"""


def format_chunks(chunks: list[Chunk]) -> str:
    if not chunks:
        return "(No code excerpts are available for this question.)"
    parts = []
    for c in chunks:
        parts.append(
            f"### chunk {c.id}: {c.filename}:{c.start_line}-{c.end_line}\n"
            f"```{c.language or ''}\n{c.content}\n```"
        )
    return "\n\n".join(parts)


def build_grade_prompt(turn: Turn, previous: Turn | None, chunks: list[Chunk]) -> str:
    parts = ["## Code excerpts", format_chunks(chunks)]
    if previous is not None:
        parts += [
            "## Previous exchange (context only)",
            f"Interviewer: {previous.question_text}",
            f"Candidate: {previous.answer_text or '(no answer)'}",
        ]
    parts += [
        "## Answer to grade",
        f"Interviewer: {turn.question_text}",
        f"Candidate: {turn.answer_text}",
    ]
    return "\n\n".join(parts)


def build_summary_prompt(graded: list[dict]) -> str:
    """`graded` holds only graded turn evaluations (see pipeline.py)."""
    blocks = []
    files: set[str] = set()
    for e in graded:
        turn_files = sorted({s["filename"] for s in e["sources"]})
        files.update(turn_files)
        blocks.append(
            "\n".join(
                [
                    f"### Question {e['seq']}: {e['question']}",
                    f"Correctness {e['correctness']['score']}/5, clarity {e['clarity']['score']}/5",
                    "Strengths: " + ("; ".join(e["strengths"]) or "none"),
                    "Gaps: " + ("; ".join(e["gaps"]) or "none"),
                    "Files: " + (", ".join(turn_files) or "none"),
                ]
            )
        )
    return "\n\n".join(
        ["## Graded questions", *blocks, "## Files you may list", "\n".join(sorted(files)) or "none"]
    )
