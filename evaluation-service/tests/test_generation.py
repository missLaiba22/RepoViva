"""run_generation and startup resume with a fake store, sources and LLM."""

import httpx

from evaluation_service.generation import Dependencies, resume_generating, run_generation
from evaluation_service.reports import PendingReport
from tests.fakes import FakeReportStore, FakeRepository, FakeVoice, chunk, grade, make_llm, turn

NOTES = {"strengths": ["s"], "improvements": ["i"], "files_to_revisit": []}


def generating(interview_id: int, repository_id: int = 15) -> dict:
    return {
        "interview_id": interview_id,
        "repository_id": repository_id,
        "partial": False,
        "status": "generating",
    }


def deps(store, *script, voice=None) -> Dependencies:
    llm, _ = make_llm(*script)
    return Dependencies(
        store=store,
        voice=voice or FakeVoice([turn(1, chunk_ids=[1])]),
        repository=FakeRepository([chunk(1)]),
        llm=llm,
    )


class BrokenVoice:
    async def get_turns(self, interview_id):
        raise httpx.ConnectError("connection refused")


async def test_success_marks_ready():
    store = FakeReportStore({7: generating(7)})

    await run_generation(PendingReport(7, 15, False), deps(store, grade(), NOTES))

    assert store.rows[7]["status"] == "ready"
    assert store.rows[7]["model"] == "test-model"
    assert store.rows[7]["summary"]["turns_graded"] == 1


async def test_upstream_failure_marks_failed_without_raising():
    store = FakeReportStore({7: generating(7)})

    await run_generation(PendingReport(7, 15, False), deps(store, voice=BrokenVoice()))

    assert store.rows[7]["status"] == "failed"
    assert store.rows[7]["error_message"] == "ConnectError: connection refused"


async def test_error_message_is_truncated():
    class LongError:
        async def get_turns(self, interview_id):
            raise RuntimeError("x" * 2000)

    store = FakeReportStore({7: generating(7)})

    await run_generation(PendingReport(7, 15, False), deps(store, voice=LongError()))

    assert len(store.rows[7]["error_message"]) == 500


async def test_store_failure_while_marking_failed_is_swallowed():
    class StoreDown(FakeReportStore):
        async def mark_failed(self, interview_id, error_message):
            raise OSError("db down")

    store = StoreDown({7: generating(7)})

    # Must not raise: it runs as a background task with no one to catch it.
    await run_generation(PendingReport(7, 15, False), deps(store, voice=BrokenVoice()))

    assert store.rows[7]["status"] == "generating"  # left for startup resume


async def test_resume_finishes_every_generating_report():
    store = FakeReportStore(
        {
            7: generating(7),
            8: {**generating(8), "status": "ready"},
            9: generating(9),
        }
    )

    await resume_generating(deps(store, grade(), NOTES, grade(), NOTES))

    assert {i: r["status"] for i, r in store.rows.items()} == {7: "ready", 8: "ready", 9: "ready"}


async def test_resume_with_nothing_pending_makes_no_calls():
    store = FakeReportStore({8: {**generating(8), "status": "ready"}})

    # An empty script: any LLM call would fail on pop().
    await resume_generating(deps(store))

    assert store.rows[8]["status"] == "ready"


async def test_resume_survives_unreachable_database():
    class StoreDown(FakeReportStore):
        async def list_generating(self):
            raise OSError("db down")

    await resume_generating(deps(StoreDown()))
