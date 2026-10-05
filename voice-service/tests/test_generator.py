from types import SimpleNamespace

import pytest

from voice_service.clients.repository import Chunk
from voice_service.llm.generator import EmptyQuestionError, QuestionGenerator, clean_question
from voice_service.llm.prompts import Exchange, build_user_prompt

CHUNK = Chunk(
    id=1, content="def consume(): ...", filename="core/service.py",
    start_line=10, end_line=20, language="python", similarity=0.9,
)


def _fake_completion(reply: str, calls: list):
    async def completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])
    return completion


async def test_generator_sends_system_and_grounded_user_prompt():
    calls = []
    gen = QuestionGenerator(model="groq/m", api_key="k", completion=_fake_completion("Why X?", calls))

    assert await gen.generate_question([], [CHUNK]) == "Why X?"
    kwargs = calls[0]
    assert kwargs["model"] == "groq/m"
    assert kwargs["api_key"] == "k"
    assert kwargs["messages"][0]["role"] == "system"
    assert "core/service.py:10-20" in kwargs["messages"][1]["content"]


async def test_generator_rejects_empty_reply():
    gen = QuestionGenerator(model="m", api_key="k", completion=_fake_completion("  ", []))
    with pytest.raises(EmptyQuestionError):
        await gen.generate_question([], [CHUNK])


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("Question: Why a single UPDATE?", "Why a single UPDATE?"),
        ('"Why a single UPDATE?"', "Why a single UPDATE?"),
        ("**Q1:** Why?", "Why?"),
        ("Why not a queue?", "Why not a queue?"),
    ],
)
def test_clean_question(raw, clean):
    assert clean_question(raw) == clean


def test_follow_up_prompt_includes_history():
    prompt = build_user_prompt([Exchange("Why X?", "Because Y.")], [CHUNK])
    assert "Q1: Why X?" in prompt
    assert "A1: Because Y." in prompt
