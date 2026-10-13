"""The `plan.requested` job contract and its handler (decision 057)."""

import pytest
from pydantic import ValidationError
from repoviva_common.messaging import build_message

from voice_service import worker


def test_plan_requested_contract():
    job = worker.PlanRequested.model_validate({"interview_id": 7, "repository_id": 15})
    assert (job.interview_id, job.repository_id) == (7, 15)
    with pytest.raises(ValidationError):
        worker.PlanRequested.model_validate({"interview_id": 7})


async def test_handler_claims_then_plans(monkeypatch):
    calls: list[tuple] = []

    class FakeStore:
        def __init__(self, db):
            pass

        async def claim_plan(self, *, interview_id, repository_id):
            calls.append(("claim", interview_id, repository_id))
            return False  # e.g. left `generating` by a crash: run_planning still runs

    async def fake_run_planning(interview_id):
        calls.append(("run", interview_id))

    monkeypatch.setattr(worker, "SessionStore", FakeStore)
    monkeypatch.setattr(worker, "get_db", lambda: None)
    monkeypatch.setattr(worker, "run_planning", fake_run_planning)

    await worker.handle_plan_requested(
        build_message("plan.requested", {"interview_id": 7, "repository_id": 15})
    )

    assert calls == [("claim", 7, 15), ("run", 7)]
