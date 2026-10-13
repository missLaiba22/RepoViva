"""Write the question plan in one LLM call (decision 052)."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

import litellm
from pydantic import BaseModel, Field, ValidationError

from voice_service.config import get_settings
from voice_service.planning.prompts import SYSTEM_PROMPT, AreaContext, build_user_prompt
from voice_service.session.store import PlannedQuestion

logger = logging.getLogger(__name__)

# litellm prints a "Give Feedback / Get Help" banner on every provider error.
litellm.suppress_debug_info = True

# litellm.acompletion's shape; injectable so tests never call a provider.
Completion = Callable[..., Awaitable[Any]]

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


class UnusablePlanError(Exception):
    """The model's reply wasn't a valid plan. Transient: worth one retry."""


class _Question(BaseModel):
    area: int
    topic: str = Field(min_length=1)
    text: str = Field(min_length=1)


class _Plan(BaseModel):
    questions: list[_Question]


class Planner:
    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        completion: Completion = litellm.acompletion,
        temperature: float = 0.7,
        # Six questions take about 500 output tokens. Groq's free tier allows
        # 1,000 output tokens per minute for the planner model, and rejects a
        # request whose max_tokens alone exceeds what is left.
        max_tokens: int = 800,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._completion = completion
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def write_plan(self, areas: list[AreaContext]) -> list[PlannedQuestion]:
        """One question per area, in the model's order (architecture → details).

        Raises UnusablePlanError for a reply that isn't one valid question
        per area. Provider errors (timeout, 429) propagate.
        """
        response = await self._completion(
            model=self._model,
            api_key=self._api_key,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(areas)},
            ],
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            response_format={"type": "json_object"},
        )
        usage = getattr(response, "usage", None)
        # Decision 052: measure the planning call against the ~5,000 estimate.
        logger.info(
            "plan call used %s tokens (%s output)",
            getattr(usage, "total_tokens", "?"), getattr(usage, "completion_tokens", "?"),
        )
        return parse_plan(response.choices[0].message.content or "", areas)


def parse_plan(content: str, areas: list[AreaContext]) -> list[PlannedQuestion]:
    try:
        plan = _Plan.model_validate_json(_FENCE.sub("", content))
    except ValidationError as exc:
        raise UnusablePlanError(f"invalid plan JSON: {exc.errors()[:3]}") from exc

    numbers = [q.area for q in plan.questions]
    if sorted(numbers) != list(range(1, len(areas) + 1)):
        raise UnusablePlanError(f"expected one question per area 1..{len(areas)}, got {numbers}")

    return [
        PlannedQuestion(
            seq=seq,
            area=areas[q.area - 1].path,
            topic=q.topic.strip(),
            text=_clean(q.text),
            chunk_ids=[c.id for c in areas[q.area - 1].chunks],
        )
        for seq, q in enumerate(plan.questions, start=1)
    ]


def _clean(text: str) -> str:
    """Strip wrapping quotes; the text goes straight to the user."""
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def get_planner() -> Planner:
    settings = get_settings()
    return Planner(model=settings.llm_model, api_key=settings.groq_api_key)
