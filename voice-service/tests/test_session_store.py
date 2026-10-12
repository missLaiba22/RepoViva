"""SessionStore against a real MongoDB (decision 053).

Needs `docker compose up mongodb`; skipped when MongoDB isn't reachable.
Each test gets its own throwaway database.
"""

from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from voice_service.config import get_settings
from voice_service.db import SESSIONS
from voice_service.session.store import PlannedQuestion, PlanState, SessionStore

PLAN = [
    PlannedQuestion(
        seq=1, area="api/", topic="orders", text="What if two orders race?", chunk_ids=[1, 2]
    ),
    PlannedQuestion(
        seq=2, area="web/", topic="retries", text="What if the page loads twice?", chunk_ids=[3]
    ),
]


@pytest.fixture
async def store():
    client = AsyncMongoClient(get_settings().mongodb_uri, serverSelectionTimeoutMS=1000)
    try:
        await client.admin.command("ping")
    except PyMongoError:
        await client.close()
        pytest.skip("MongoDB not reachable")
    name = f"voice_test_{uuid4().hex[:8]}"
    db = client[name]
    await db[SESSIONS].create_index("interview_id", unique=True)
    yield SessionStore(db)
    await client.drop_database(name)
    await client.close()


async def test_claim_is_idempotent_until_failed(store):
    assert await store.claim_plan(interview_id=7, repository_id=15) is True
    # generating: a repeated trigger does nothing
    assert await store.claim_plan(interview_id=7, repository_id=15) is False

    await store.fail_plan(7, "TimeoutError: groq", retryable=True)
    assert await store.get_plan_state(7) == PlanState(
        plan_status="failed", error_message="TimeoutError: groq", retryable=True
    )
    # failed: Try again restarts it, clean
    assert await store.claim_plan(interview_id=7, repository_id=15) is True
    assert (await store.get_plan_job(7)).plan_status == "generating"
    assert (await store.get_plan_state(7)).error_message is None

    await store.save_plan(7, PLAN)
    # ready: never restarted
    assert await store.claim_plan(interview_id=7, repository_id=15) is False
    loaded = await store.load_plan(7)
    assert [PlannedQuestion(**q.model_dump(include=set(PlannedQuestion.model_fields)))
            for q in loaded] == PLAN
    assert {q.status for q in loaded} == {"planned"}


async def test_a_stale_job_cannot_overwrite_a_ready_plan(store):
    await store.claim_plan(interview_id=7, repository_id=15)
    await store.save_plan(7, PLAN)

    await store.fail_plan(7, "late failure", retryable=True)

    assert (await store.get_plan_state(7)).plan_status == "ready"


async def test_plan_is_not_loaded_until_ready(store):
    await store.claim_plan(interview_id=7, repository_id=15)

    assert await store.load_plan(7) is None
    assert await store.list_generating() == [7]


async def test_turns_list_only_asked_questions_in_the_evaluation_shape(store):
    await store.claim_plan(interview_id=7, repository_id=15)
    await store.save_plan(7, PLAN)
    assert await store.list_turns(7) == []

    await store.mark_asked(7, 1)
    await store.add_timings(7, 1, {"tts_ms": 900})
    await store.record_answer(7, 1, "With a row lock.")
    await store.mark_asked(7, 2)

    assert await store.list_turns(7) == [
        {"seq": 1, "question_text": "What if two orders race?", "answer_text": "With a row lock.",
         "status": "answered", "retrieved_chunk_ids": [1, 2]},
        {"seq": 2, "question_text": "What if the page loads twice?", "answer_text": None,
         "status": "asked", "retrieved_chunk_ids": [3]},
    ]


async def test_an_answer_is_recorded_once(store):
    await store.claim_plan(interview_id=7, repository_id=15)
    await store.save_plan(7, PLAN)
    await store.mark_asked(7, 1)
    await store.record_answer(7, 1, "first")

    with pytest.raises(RuntimeError):
        await store.record_answer(7, 1, "second")
