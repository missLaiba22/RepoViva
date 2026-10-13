"""The worker's message contracts and the claim rule under redelivery (decision 057)."""

import pytest
from pydantic import ValidationError
from repoviva_common.messaging import build_message

from evaluation_service import generation, worker
from evaluation_service.generation import Dependencies, request_report
from evaluation_service.reports import PendingReport
from tests.fakes import FakeReportStore

REPORT = PendingReport(interview_id=7, repository_id=15, partial=False)


@pytest.fixture
def runs(monkeypatch):
    ran: list[PendingReport] = []

    async def record(report, deps=None):
        ran.append(report)

    monkeypatch.setattr(generation, "run_generation", record)
    return ran


def deps(store) -> Dependencies:
    return Dependencies(store=store, voice=None, repository=None, llm=None)


def row(status: str) -> dict:
    return {"interview_id": 7, "repository_id": 15, "partial": False, "status": status}


def test_interview_ended_contract():
    event = worker.InterviewEnded.model_validate(
        {"interview_id": 7, "repository_id": 15, "outcome": "interrupted", "error_message": "x"}
    )
    assert worker._pending(event) == PendingReport(7, 15, partial=True)
    with pytest.raises(ValidationError):
        worker.InterviewEnded.model_validate({"interview_id": 7, "outcome": "completed"})


def test_report_requested_contract():
    with pytest.raises(ValidationError):
        worker.ReportRequested.model_validate(
            {"interview_id": 7, "repository_id": 15, "outcome": "active"}
        )


async def test_new_report_is_generated(runs):
    store = FakeReportStore()

    await request_report(REPORT, deps(store))

    assert runs == [REPORT]
    assert store.rows[7]["status"] == "generating"


async def test_ready_report_is_skipped(runs):
    await request_report(REPORT, deps(FakeReportStore({7: row("ready")})))

    assert runs == []


@pytest.mark.parametrize("status", ["generating", "failed"])
async def test_unfinished_or_failed_report_reruns(runs, status):
    # `generating` here means the attempt holding the message died.
    await request_report(REPORT, deps(FakeReportStore({7: row(status)})))

    assert runs == [REPORT]


async def test_event_and_job_take_the_same_path(monkeypatch):
    requested: list[PendingReport] = []

    async def record(report):
        requested.append(report)

    monkeypatch.setattr(worker, "request_report", record)
    data = {"interview_id": 7, "repository_id": 15, "outcome": "completed"}

    await worker.handle_interview_ended(build_message("interview.ended", data))
    await worker.handle_report_requested(build_message("report.requested", data))

    assert requested == [REPORT, REPORT]
