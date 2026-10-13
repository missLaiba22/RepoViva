"""run_generation with a fake store, sources and LLM."""

import httpx
import pytest

from evaluation_service.generation import Dependencies, run_generation
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


async def test_store_failure_while_marking_failed_raises_for_redelivery():
    class StoreDown(FakeReportStore):
        async def mark_failed(self, interview_id, error_message):
            raise OSError("db down")

    store = StoreDown({7: generating(7)})

    # Raises so the worker keeps the message and SQS redelivers it.
    with pytest.raises(OSError):
        await run_generation(PendingReport(7, 15, False), deps(store, voice=BrokenVoice()))

    assert store.rows[7]["status"] == "generating"
