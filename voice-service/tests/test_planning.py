"""The planning job (decision 052): idempotency, retry, failure kinds, and plan parsing."""

import json
from types import SimpleNamespace

import pytest

from voice_service.clients.repository import Area, Chunk
from voice_service.planning.job import Dependencies, run_planning
from voice_service.planning.planner import Planner, UnusablePlanError, parse_plan
from voice_service.planning.prompts import AreaContext
from voice_service.session.store import PlanJob, PlannedQuestion


def chunk(id_, filename):
    return Chunk(id_, "code", filename, 1, 9, "python", 0.9)


class FakeStore:
    def __init__(self, plan_status="generating"):
        self.plan_status = plan_status
        self.attempts = 0
        self.saved: list[PlannedQuestion] | None = None
        self.failed: tuple[str, bool] | None = None

    async def get_plan_job(self, interview_id):
        return PlanJob(interview_id=interview_id, repository_id=15, plan_status=self.plan_status)

    async def count_attempt(self, interview_id):
        self.attempts += 1

    async def save_plan(self, interview_id, questions):
        self.saved = questions

    async def fail_plan(self, interview_id, error_message, *, retryable):
        self.failed = (error_message, retryable)


class FakeRepository:
    def __init__(self, areas, chunks_by_prefix):
        self._areas = areas
        self._chunks = chunks_by_prefix
        self.prefixes: list[str] = []

    async def list_areas(self, repository_id, *, limit):
        return self._areas[:limit]

    async def retrieve(self, repository_id, query, *, top_k, filename_prefix):
        self.prefixes.append(filename_prefix)
        return self._chunks.get(filename_prefix, [])[:top_k]


class FakePlanner:
    """Fails the first `failures` calls, then returns one question per area."""

    def __init__(self, failures=0):
        self._failures = failures
        self.calls: list[list[AreaContext]] = []

    async def write_plan(self, areas):
        self.calls.append(areas)
        if len(self.calls) <= self._failures:
            raise TimeoutError("groq timed out")
        return [
            PlannedQuestion(
                seq=i, area=a.path, topic="t", text=f"Q{i}?", chunk_ids=[c.id for c in a.chunks]
            )
            for i, a in enumerate(areas, start=1)
        ]


AREAS = [Area("api/", 30), Area("web/", 20), Area("docs/", 5)]
CHUNKS = {"api/": [chunk(1, "api/a.py"), chunk(2, "api/b.py")], "web/": [chunk(3, "web/c.ts")]}


def deps(store, planner=None, areas=AREAS, chunks=CHUNKS):
    return Dependencies(
        store=store,
        repository=FakeRepository(areas, chunks),
        planner=planner or FakePlanner(),
        max_questions=6,
        chunks_per_area=2,
    )


async def test_plan_is_written_from_areas_with_code():
    store = FakeStore()
    d = deps(store)

    await run_planning(7, d)

    # docs/ had no chunks, so it gets no question.
    assert [(q.area, q.chunk_ids) for q in store.saved] == [("api/", [1, 2]), ("web/", [3])]
    assert d.repository.prefixes == ["api/", "web/", "docs/"]
    assert store.failed is None


@pytest.mark.parametrize("plan_status", ["ready", "failed"])
async def test_rerun_does_nothing_unless_generating(plan_status):
    store = FakeStore(plan_status)
    planner = FakePlanner()

    await run_planning(7, deps(store, planner))

    assert planner.calls == []
    assert store.attempts == 0
    assert store.saved is None and store.failed is None


async def test_transient_failure_is_retried_once():
    store = FakeStore()

    await run_planning(7, deps(store, FakePlanner(failures=1)))

    assert store.attempts == 2
    assert store.saved is not None


async def test_second_transient_failure_fails_retryable():
    store = FakeStore()

    await run_planning(7, deps(store, FakePlanner(failures=2)))

    assert store.attempts == 2
    message, retryable = store.failed
    assert retryable is True
    assert "groq timed out" in message


@pytest.mark.parametrize(
    ("areas", "chunks"),
    [([], {}), ([Area("docs/", 5)], {})],  # no areas; areas but no code in any
)
async def test_nothing_to_ask_fails_permanently_without_retry(areas, chunks):
    store = FakeStore()
    planner = FakePlanner()

    await run_planning(7, deps(store, planner, areas=areas, chunks=chunks))

    assert store.attempts == 1
    assert planner.calls == []
    _, retryable = store.failed
    assert retryable is False


# --- The LLM's reply -----------------------------------------------------------

CONTEXTS = [
    AreaContext("api/", [chunk(1, "api/a.py")]),
    AreaContext("web/", [chunk(3, "web/c.ts"), chunk(4, "web/d.ts")]),
]


def reply(*questions):
    return json.dumps({"questions": [
        {"area": area, "topic": "a topic", "text": text} for area, text in questions
    ]})


def test_parse_keeps_model_order_and_maps_areas():
    plan = parse_plan(reply((2, '"What if the page loads twice?"'), (1, "Why a queue?")), CONTEXTS)

    assert [(q.seq, q.area, q.text, q.chunk_ids) for q in plan] == [
        (1, "web/", "What if the page loads twice?", [3, 4]),
        (2, "api/", "Why a queue?", [1]),
    ]


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        reply((1, "Only one?")),  # an area left out
        reply((1, "A?"), (1, "B?")),  # an area twice
        reply((1, "A?"), (3, "B?")),  # no area 3
        reply((1, "A?"), (2, "")),  # empty question
    ],
)
def test_parse_rejects_anything_but_one_question_per_area(content):
    with pytest.raises(UnusablePlanError):
        parse_plan(content, CONTEXTS)


async def test_planner_asks_for_json_and_sends_every_area():
    calls = []

    async def completion(**kwargs):
        calls.append(kwargs)
        content = reply((1, "A?"), (2, "B?"))
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(total_tokens=1234),
        )

    planner = Planner(model="groq/m", api_key="k", completion=completion)

    assert [q.text for q in await planner.write_plan(CONTEXTS)] == ["A?", "B?"]
    kwargs = calls[0]
    assert kwargs["response_format"] == {"type": "json_object"}
    user_prompt = kwargs["messages"][1]["content"]
    assert "Area 1: api/" in user_prompt and "Area 2: web/" in user_prompt
    assert "web/c.ts:1-9" in user_prompt


async def test_failure_that_cannot_be_stored_raises_for_redelivery():
    class StoreDown(FakeStore):
        async def fail_plan(self, interview_id, error_message, *, retryable):
            raise OSError("mongo down")

    # Raises so the worker keeps the message and SQS redelivers it.
    with pytest.raises(OSError):
        await run_planning(7, deps(StoreDown(), planner=FakePlanner(failures=2)))
