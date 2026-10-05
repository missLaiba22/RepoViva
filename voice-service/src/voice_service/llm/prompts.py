"""Prompt text for question generation (decision 034).

Kept apart from the call itself so prompts can be read, diffed and
tuned without touching transport code.
"""

from __future__ import annotations

from dataclasses import dataclass

from voice_service.clients.repository import Chunk

SYSTEM_PROMPT = """\
You are a senior software engineer running a mock technical interview. \
The candidate wrote the code you are shown — it comes from their own \
repository — and you are testing whether they can explain and defend it.

Rules:
- Ask exactly ONE question per reply. No preamble, no feedback on the \
previous answer, no numbering.
- Ground every question in the code excerpts provided: name the specific \
file, function, class or design choice you are asking about.
- Prefer "why" and "what would happen if" questions over "what does this \
do": design decisions, trade-offs, failure modes, edge cases, scaling, \
testing.
- If the candidate's last answer was vague, wrong or incomplete, follow \
up on that same point before moving on.
- Never repeat a question already asked in this interview.
- Your reply will be spoken aloud: plain sentences only, no markdown, no \
code blocks, no bullet points, at most 45 words."""

# Decision 042: what to retrieve before the candidate has said anything.
OPENING_SEED_QUERY = "application entry point, core architecture, main modules and how they connect"


@dataclass(frozen=True)
class Exchange:
    """One question and, if given, its answer — the history the model sees."""

    question: str
    answer: str | None


def format_chunks(chunks: list[Chunk]) -> str:
    if not chunks:
        return "(No code excerpts were found for this part of the conversation.)"
    parts = []
    for c in chunks:
        lang = c.language or ""
        parts.append(f"### {c.filename}:{c.start_line}-{c.end_line}\n```{lang}\n{c.content}\n```")
    return "\n\n".join(parts)


def format_history(history: list[Exchange]) -> str:
    lines = []
    for i, ex in enumerate(history, start=1):
        lines.append(f"Q{i}: {ex.question}")
        lines.append(f"A{i}: {ex.answer if ex.answer is not None else '(no answer)'}")
    return "\n".join(lines)


def build_user_prompt(history: list[Exchange], chunks: list[Chunk]) -> str:
    code = format_chunks(chunks)
    if not history:
        task = (
            "This is the start of the interview. Ask an opening question about "
            "the overall structure or a central design decision visible in this code."
        )
        return f"Code excerpts from the candidate's repository:\n\n{code}\n\n{task}"

    task = (
        "Ask the next question. Follow up on the last answer if it needs probing; "
        "otherwise move to a new aspect of the code above."
    )
    return (
        f"Interview so far:\n{format_history(history)}\n\n"
        f"Code excerpts relevant to the last answer:\n\n{code}\n\n{task}"
    )
