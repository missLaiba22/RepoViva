"""Shared fakes: a scripted LLM, and in-memory Voice and Repository sources."""

from __future__ import annotations

import json
from types import SimpleNamespace

from evaluation_service.clients.repository import Chunk
from evaluation_service.clients.voice import Turn
from evaluation_service.grading.llm import JsonLlm


def reply(content: str) -> SimpleNamespace:
    """The slice of a litellm response the code reads."""
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class ScriptedCompletion:
    """Returns (or raises) each scripted item in turn and records every call."""

    def __init__(self, *script):
        self._script = list(script)
        self.calls: list[dict] = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return reply(item if isinstance(item, str) else json.dumps(item))


class RecordingSleep:
    def __init__(self):
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def make_llm(*script) -> tuple[JsonLlm, ScriptedCompletion]:
    completion = ScriptedCompletion(*script)
    llm = JsonLlm(model="test-model", api_key="k", completion=completion, sleep=RecordingSleep())
    return llm, completion


def grade(*, correctness=4, clarity=3, key_points=None, evidence=None) -> dict:
    return {
        "correctness": {"score": correctness, "justification": "matches the locking code"},
        "clarity": {"score": clarity, "justification": "a bit roundabout"},
        "strengths": ["You named the row lock."],
        "gaps": ["You didn't say what the second buyer sees."],
        "key_points": key_points
        if key_points is not None
        else [{"point": "Stock is locked with SELECT ... FOR UPDATE", "chunk_ids": [1]}],
        "evidence_chunk_ids": evidence if evidence is not None else [1],
    }


def chunk(i: int, filename: str = "orders/service.py") -> Chunk:
    return Chunk(
        id=i, content=f"# code {i}", filename=filename, start_line=i, end_line=i + 9, language="python"
    )


def turn(seq: int, *, answer: str | None = "An answer.", chunk_ids=(1, 2)) -> Turn:
    return Turn(
        seq=seq,
        question_text=f"Question {seq}?",
        answer_text=answer,
        status="answered" if answer is not None else "asked",
        retrieved_chunk_ids=list(chunk_ids),
    )


class FakeVoice:
    def __init__(self, turns):
        self._turns = turns

    async def get_turns(self, interview_id):
        return self._turns


class FakeRepository:
    def __init__(self, chunks):
        self._chunks = {c.id: c for c in chunks}
        self.requested: list[list[int]] = []

    async def get_chunks(self, repository_id, ids):
        self.requested.append(list(ids))
        return {i: self._chunks[i] for i in ids if i in self._chunks}
