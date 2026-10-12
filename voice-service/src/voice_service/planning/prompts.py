"""Prompt text for the question plan (decisions 048, 052).

Kept apart from the call itself so prompts can be read, diffed and
tuned without touching transport code.
"""

from __future__ import annotations

from dataclasses import dataclass

from voice_service.clients.repository import Chunk

# What to retrieve from each area: its main logic, not tests or config.
AREA_QUERY = "core logic, main responsibilities and how this part of the system works"

SYSTEM_PROMPT = """\
You are a friendly but rigorous senior engineer preparing a mock interview \
about a project the candidate built. You are shown excerpts from the \
major areas of their repository so that you understand how the project \
works. Treat them as background knowledge, not as the subject of your \
questions.

Write the whole interview in advance: exactly one question for each area, \
ordered from the overall architecture down to details.

Ask scenario-based questions: put the candidate in a realistic situation \
their project faces, and ask how it behaves or how they would handle it. \
For example: two users doing the same thing at the same moment, a \
service or third party failing halfway through, traffic growing tenfold, \
bad or unexpected input, a teammate wanting to change the design, or why \
they chose one approach over another.

Rules for every question:
- Exactly ONE question, asking about one thing. Never join two questions \
with "and". No numbering.
- Describe situations in everyday product and system terms, such as "when \
two customers buy the last item at once". Refer to parts of the project \
by plain names like "your checkout" or "the payment webhook". Never \
quote code or name files, functions, classes or variables.
- Every situation must be one this project really faces, based on the \
excerpts. No generic textbook questions.
- Prefer how and why: decisions, trade-offs, what could go wrong, how \
they would notice it and fix it, what they would do differently.
- No two questions about the same situation.
- The first question is an easy warm-up about what the project does.
- Each question is spoken aloud and heard only once, so keep it short: \
plain conversational sentences, no markdown, at most two sentences and \
35 words in total.

Reply with JSON only, in this shape:
{"questions": [{"area": <area number>, "topic": "<two to five words>", \
"text": "<the question>"}]}"""


@dataclass(frozen=True)
class AreaContext:
    """One area and the code retrieved from it."""

    path: str
    chunks: list[Chunk]


def build_user_prompt(areas: list[AreaContext]) -> str:
    parts = []
    for number, area in enumerate(areas, start=1):
        code = "\n\n".join(
            f"### {c.filename}:{c.start_line}-{c.end_line}\n```{c.language or ''}\n{c.content}\n```"
            for c in area.chunks
        )
        parts.append(f"## Area {number}: {area.path}\n\n{code}")
    return (
        "Background: excerpts from the candidate's repository, grouped by area.\n\n"
        + "\n\n".join(parts)
        + f"\n\nWrite {len(areas)} questions, one per area."
    )
