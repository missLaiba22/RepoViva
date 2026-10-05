"""Question generation via litellm (decisions 034, 038)."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

import litellm

from voice_service.clients.repository import Chunk
from voice_service.config import get_settings
from voice_service.llm.prompts import SYSTEM_PROMPT, Exchange, build_user_prompt

# litellm.acompletion's shape; injectable so tests never call a provider.
Completion = Callable[..., Awaitable[Any]]

# Labels a model sometimes prepends despite the prompt ("Question: ...").
_LABEL_PREFIX = re.compile(r"^\s*(?:\*\*)?(?:question|interviewer|q\d*)\s*[:\-]\s*(?:\*\*)?", re.IGNORECASE)


class EmptyQuestionError(Exception):
    """The model returned nothing usable."""


def clean_question(text: str) -> str:
    """Strip labels and wrapping quotes; the text goes straight to the user."""
    text = _LABEL_PREFIX.sub("", text.strip()).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


class QuestionGenerator:
    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        completion: Completion = litellm.acompletion,
        temperature: float = 0.7,
        max_tokens: int = 200,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._completion = completion
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def generate_question(self, history: list[Exchange], chunks: list[Chunk]) -> str:
        """Next question given the conversation so far and fresh code context.

        Provider errors propagate: the runner treats them as a failed
        session (decision 041 → `interrupted`).
        """
        response = await self._completion(
            model=self._model,
            api_key=self._api_key,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(history, chunks)},
            ],
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        question = clean_question(response.choices[0].message.content or "")
        if not question:
            raise EmptyQuestionError("LLM returned an empty question")
        return question


def get_question_generator() -> QuestionGenerator:
    settings = get_settings()
    return QuestionGenerator(model=settings.llm_model, api_key=settings.groq_api_key)
