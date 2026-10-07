"""Prompt text for question generation (decisions 034, 048).

Kept apart from the call itself so prompts can be read, diffed and
tuned without touching transport code.
"""

from __future__ import annotations

from dataclasses import dataclass

from voice_service.clients.repository import Chunk

SYSTEM_PROMPT = """\
You are a friendly but rigorous senior engineer running a mock interview \
about a project the candidate built. You are shown excerpts from their \
repository so that you understand how the project works. Treat them as \
background knowledge, not as the subject of your questions (decision 048).

Ask scenario-based questions: put the candidate in a realistic situation \
their project faces, and ask how it behaves or how they would handle it. \
For example: two users doing the same thing at the same moment, a \
service or third party failing halfway through, traffic growing tenfold, \
bad or unexpected input, a teammate wanting to change the design, or why \
they chose one approach over another.

Rules:
- Every reply ends with exactly ONE question, asking about one thing. \
Never join two questions with "and". No numbering.
- Never judge the previous answer ("that was vague", "you just restated \
it"). At most a few neutral words before the question, like "Okay." or \
"Let's try another angle."
- Describe situations in everyday product and system terms, such as "when \
two customers buy the last item at once". Refer to parts of the project \
by plain names like "your checkout" or "the payment webhook". Never \
quote code or name files, functions, classes or variables.
- Every situation must be one this project really faces, based on the \
excerpts. No generic textbook questions.
- Prefer how and why: decisions, trade-offs, what could go wrong, how \
they would notice it and fix it, what they would do differently.
- If the last answer was vague, ask one simpler, more concrete follow-up \
about the same situation.
- If the candidate says they don't know, or asks you to answer for them, \
don't press or repeat yourself. Give a hint of one short sentence that \
points in the right direction without explaining the solution, then ask \
an easier question. Or move to a different situation. This is practice: \
they learn by working it out.
- Never repeat a situation already covered in this interview.
- Your reply will be spoken aloud and heard only once, so keep it short: \
plain conversational sentences, no markdown, at most two sentences and \
35 words in total."""

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
            "This is the start of the interview. Open with a situation at the heart "
            "of what this project does, as an easy warm-up."
        )
        return f"Background: excerpts from the candidate's repository.\n\n{code}\n\n{task}"

    task = (
        "Ask the next question. Follow up on the last answer if it needs probing; "
        "otherwise move to a new situation that the background above suggests."
    )
    return (
        f"Interview so far:\n{format_history(history)}\n\n"
        f"Background: repository excerpts related to the last answer.\n\n{code}\n\n{task}"
    )
