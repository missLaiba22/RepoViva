"""JsonLlm's retry rules (decisions 050, 051), with a scripted provider."""

import json
from types import SimpleNamespace

import httpx
import litellm
import pytest

from evaluation_service.grading.models import TurnGrade
from tests.fakes import grade, make_llm


def rate_limited(retry_after: str | None = None) -> litellm.RateLimitError:
    headers = {"retry-after": retry_after} if retry_after else {}
    response = httpx.Response(429, headers=headers, request=httpx.Request("POST", "http://groq"))
    return litellm.RateLimitError("slow down", llm_provider="groq", model="m", response=response)


async def complete(llm):
    return await llm.complete(system="s", user="u", schema=TurnGrade)


async def test_valid_reply_is_parsed_and_request_is_json_mode():
    llm, completion = make_llm(grade())

    result = await complete(llm)

    assert result.correctness.score == 4
    call = completion.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert call["reasoning_effort"] == "low"
    assert call["model"] == "test-model"


async def test_fenced_json_is_accepted():
    llm, _ = make_llm("```json\n" + json.dumps(grade()) + "\n```")

    assert (await complete(llm)) is not None


async def test_invalid_reply_is_retried_once():
    llm, completion = make_llm("not json", grade(correctness=2))

    result = await complete(llm)

    assert result.correctness.score == 2
    assert len(completion.calls) == 2


async def test_two_unusable_replies_give_none():
    # The second is valid JSON but a score of 9 is out of range.
    llm, completion = make_llm("{", grade(correctness=9))

    assert (await complete(llm)) is None
    assert len(completion.calls) == 2


async def test_rate_limit_waits_retry_after_then_succeeds():
    llm, completion = make_llm(rate_limited("7"), rate_limited(), grade())

    result = await complete(llm)

    assert result is not None
    assert llm._sleep.delays == [7.0, 15.0]  # header, then the default
    assert len(completion.calls) == 3


def groq_rate_limited(message: str) -> litellm.RateLimitError:
    """Groq's shape: no retry-after header, the wait is in the message."""
    return litellm.RateLimitError(message, llm_provider="groq", model="m")


async def test_wait_is_read_from_groq_message():
    llm, _ = make_llm(groq_rate_limited("Please try again in 6.5s."), grade())

    await complete(llm)

    assert llm._sleep.delays == [6.5]


@pytest.mark.parametrize(
    "message",
    [
        "tokens per day (TPD): Limit 200000. Please try again in 8m11.18s.",
        "Please try again in 2h3m.",
    ],
)
async def test_long_waits_fail_fast(message):
    llm, completion = make_llm(groq_rate_limited(message), grade())

    with pytest.raises(litellm.RateLimitError):
        await complete(llm)
    assert llm._sleep.delays == []
    assert len(completion.calls) == 1


async def test_long_retry_after_header_fails_fast():
    llm, _ = make_llm(rate_limited("600"), grade())

    with pytest.raises(litellm.RateLimitError):
        await complete(llm)


async def test_tokens_are_counted_across_calls():
    llm, completion = make_llm(grade(), grade())

    async def with_usage(**kwargs):
        response = await completion(**kwargs)
        response.usage = SimpleNamespace(total_tokens=1234)
        return response

    llm._completion = with_usage
    await complete(llm)
    await complete(llm)

    assert llm.total_tokens == 2468


async def test_rate_limit_gives_up_after_max_waits():
    llm, _ = make_llm(*[rate_limited() for _ in range(9)])

    with pytest.raises(litellm.RateLimitError):
        await complete(llm)
    assert len(llm._sleep.delays) == 8


def json_validate_failed() -> litellm.BadRequestError:
    return litellm.BadRequestError(
        'GroqException - {"error":{"code":"json_validate_failed"}}', model="m", llm_provider="groq"
    )


async def test_provider_json_rejection_counts_as_invalid_reply():
    llm, completion = make_llm(json_validate_failed(), grade(correctness=3))

    result = await complete(llm)

    assert result.correctness.score == 3
    assert len(completion.calls) == 2


async def test_two_provider_json_rejections_give_none():
    llm, _ = make_llm(json_validate_failed(), json_validate_failed())

    assert (await complete(llm)) is None


async def test_other_bad_requests_propagate():
    error = litellm.BadRequestError("model_not_found", model="m", llm_provider="groq")
    llm, _ = make_llm(error)

    with pytest.raises(litellm.BadRequestError):
        await complete(llm)


async def test_other_provider_errors_propagate():
    error = litellm.APIConnectionError("down", llm_provider="groq", model="m")
    llm, _ = make_llm(error)

    with pytest.raises(litellm.APIConnectionError):
        await complete(llm)


async def test_extra_list_items_are_trimmed_not_rejected():
    many = [{"point": f"p{i}", "chunk_ids": [1]} for i in range(6)]
    payload = grade(key_points=many) | {"strengths": ["a", "b", "c", "d"]}
    llm, _ = make_llm(payload)

    result = await complete(llm)

    assert len(result.key_points) == 4
    assert len(result.strengths) == 3
