"""JSON-returning LLM calls via litellm, with the retry rules of decisions 050–051.

- Invalid JSON, or JSON that fails validation: one retry, then None. The
  caller marks that piece of the report as not graded. In JSON mode Groq
  checks the JSON itself and answers 400 `json_validate_failed` instead
  of returning it; that counts as invalid JSON, not a provider error.
- Rate limited (HTTP 429): wait and try again. Groq's free tier allows
  about 8,000 tokens a minute per model, so waits are expected on every
  report, not an error.
- Any other provider error propagates: the report fails and a later
  trigger regenerates it (decision 049).
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import litellm
from pydantic import BaseModel, ValidationError

from evaluation_service.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# litellm prints a "Give Feedback / Get Help" banner on every provider
# error, including each expected 429.
litellm.suppress_debug_info = True

# litellm.acompletion's shape; injectable so tests never call a provider.
Completion = Callable[..., Awaitable[Any]]
Sleep = Callable[[float], Awaitable[None]]

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")

# Used when the 429 doesn't say how long to wait. Groq's per-minute
# window refills continuously, so ~15 s frees room for one more call.
_DEFAULT_RATE_LIMIT_WAIT_S = 15.0
# A longer wait means a daily limit (Groq's free tier: 200,000 tokens a
# day per model). Waiting it out would hold the report for minutes or
# hours, so the report fails instead and a later trigger regenerates it.
_MAX_RATE_LIMIT_WAIT_S = 60.0

# Groq puts the wait in the message, not a header: "try again in 8m11.18s",
# "try again in 6.5s", "try again in 450ms".
_TRY_AGAIN = re.compile(r"try again in ((?:[\d.]+(?:h|ms|m|s))+)")
_UNIT_SECONDS = {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001}


def _retry_after(exc: Exception) -> float | None:
    """Seconds the provider asked us to wait, if it said."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or {}
    try:
        return float(headers.get("retry-after"))
    except (TypeError, ValueError):
        pass
    match = _TRY_AGAIN.search(str(exc))
    if match is None:
        return None
    parts = re.findall(r"([\d.]+)(h|ms|m|s)", match.group(1))
    return sum(float(n) * _UNIT_SECONDS[u] for n, u in parts)


class JsonLlm:
    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        completion: Completion = litellm.acompletion,
        sleep: Sleep = asyncio.sleep,
        temperature: float = 0.2,
        # gpt-oss reasons before answering, and reasoning counts against
        # max_tokens; 3000 leaves room for both at low effort.
        max_tokens: int = 3000,
        reasoning_effort: str | None = "low",
        max_rate_limit_waits: int = 8,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._completion = completion
        self._sleep = sleep
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._reasoning_effort = reasoning_effort
        self._max_rate_limit_waits = max_rate_limit_waits
        # Provider-reported tokens across every call, for logs and capacity
        # planning against the daily limit (decision 051).
        self.total_tokens = 0

    async def complete(self, *, system: str, user: str, schema: type[T]) -> T | None:
        """Parsed reply, or None after two unusable replies."""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for attempt in (1, 2):
            content = await self._call(messages)
            try:
                return schema.model_validate_json(_FENCE.sub("", content))
            except ValidationError as exc:
                logger.warning(
                    "unusable %s reply (attempt %d): %s", schema.__name__, attempt, exc.errors()[:3]
                )
        return None

    async def _call(self, messages: list[dict[str, str]]) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "api_key": self._api_key,
            "messages": messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "response_format": {"type": "json_object"},
        }
        if self._reasoning_effort:
            kwargs["reasoning_effort"] = self._reasoning_effort

        waits = 0
        while True:
            try:
                response = await self._completion(**kwargs)
            except litellm.BadRequestError as exc:
                if "json_validate_failed" not in str(exc):
                    raise
                logger.warning("provider rejected malformed JSON from the model")
                return ""
            except litellm.RateLimitError as exc:
                waits += 1
                delay = _retry_after(exc) or _DEFAULT_RATE_LIMIT_WAIT_S
                if waits > self._max_rate_limit_waits or delay > _MAX_RATE_LIMIT_WAIT_S:
                    raise
                logger.info("rate limited, waiting %.0f s (wait %d)", delay, waits)
                await self._sleep(delay)
                continue
            usage = getattr(response, "usage", None)
            self.total_tokens += getattr(usage, "total_tokens", 0) or 0
            return response.choices[0].message.content or ""


def get_llm() -> JsonLlm:
    settings = get_settings()
    return JsonLlm(model=settings.eval_llm_model, api_key=settings.groq_api_key)
