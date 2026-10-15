"""Ingestion job contract and idempotency under SQS redelivery (decisions 057, 058)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from repoviva_common.messaging import build_message

from repository_service import worker
from repository_service.ingestion import jobs, orchestrator
from repository_service.ingestion.jobs import IngestionJob, JobStatus
from repository_service.ingestion.orchestrator import CRASHED_MESSAGE, OutcomeNotPublishedError


@pytest.fixture
def pipeline(monkeypatch):
    """Fakes the job store, Core API and fetch/index. Returns the recorded calls."""
    calls = SimpleNamespace(stored={}, events=[], runs=0, publish_ok=True)

    async def fake_claim(_pool, *, repository_id, github_url):
        job = calls.stored.get(repository_id)
        if job is None:
            calls.stored[repository_id] = IngestionJob(
                repository_id, github_url, JobStatus.IN_PROGRESS,
            )
        elif job.status is JobStatus.IN_PROGRESS:
            calls.stored[repository_id] = replace(job, attempts=job.attempts + 1)

    async def fake_get(_pool, repository_id):
        return calls.stored.get(repository_id)

    async def fake_set_status(_pool, repository_id, status, error_message=None):
        job = calls.stored[repository_id]
        calls.stored[repository_id] = replace(job, status=status, error_message=error_message)

    class FakeClient:
        async def emit_event(self, repository_id, event, *, error_message=None):
            calls.events.append((event, error_message))
            return calls.publish_ok

    async def fake_ingest(_job):
        calls.runs += 1

    monkeypatch.setattr(jobs, "claim", fake_claim)
    monkeypatch.setattr(jobs, "get", fake_get)
    monkeypatch.setattr(jobs, "set_status", fake_set_status)
    monkeypatch.setattr(orchestrator, "get_db_pool", lambda: None)
    monkeypatch.setattr(worker, "get_db_pool", lambda: None)
    monkeypatch.setattr(orchestrator, "get_event_publisher", lambda: FakeClient())
    monkeypatch.setattr(
        orchestrator, "get_settings", lambda: SimpleNamespace(workspace_root=Path("/unused")),
    )
    monkeypatch.setattr(orchestrator, "_ingest", fake_ingest)
    return calls


def _job_message(repository_id: int = 14):
    return build_message(
        "ingestion.requested",
        {"repository_id": repository_id, "github_url": "https://github.com/x/y"},
    )


def test_ingestion_requested_contract():
    with pytest.raises(ValidationError):
        worker.IngestionRequested.model_validate({"repository_id": 14})
    job = worker.IngestionRequested.model_validate(_job_message().data)
    assert job.repository_id == 14


async def test_job_runs_and_is_stored_ready(pipeline):
    await worker.handle_ingestion_job(_job_message())

    assert pipeline.runs == 1
    assert pipeline.stored["14"].status is JobStatus.READY
    assert pipeline.events == [("ingestion.started", None), ("ingestion.completed", None)]


async def test_duplicate_for_finished_job_republishes_outcome_without_running(pipeline):
    await worker.handle_ingestion_job(_job_message())
    await worker.handle_ingestion_job(_job_message())

    assert pipeline.runs == 1
    assert pipeline.events[-1] == ("ingestion.completed", None)


async def test_duplicate_for_failed_job_republishes_its_error(pipeline):
    pipeline.stored["14"] = IngestionJob(
        "14", "https://github.com/x/y", JobStatus.FAILED, error_message="fetch failed: 404",
    )

    await worker.handle_ingestion_job(_job_message())

    assert pipeline.runs == 0
    assert pipeline.events == [("ingestion.failed", "fetch failed: 404")]


async def test_lost_final_event_raises_so_the_job_is_redelivered(pipeline):
    pipeline.publish_ok = False
    with pytest.raises(OutcomeNotPublishedError):
        await worker.handle_ingestion_job(_job_message())

    pipeline.publish_ok = True
    await worker.handle_ingestion_job(_job_message())

    assert pipeline.runs == 1
    assert pipeline.events[-1] == ("ingestion.completed", None)


async def test_job_that_keeps_crashing_fails_without_running_again(pipeline):
    # Two deliveries crashed mid-job; this is the third.
    pipeline.stored["14"] = IngestionJob(
        "14", "https://github.com/x/y", JobStatus.IN_PROGRESS, attempts=2,
    )

    await worker.handle_ingestion_job(_job_message())

    assert pipeline.runs == 0
    assert pipeline.stored["14"].status is JobStatus.FAILED
    assert pipeline.events == [("ingestion.failed", CRASHED_MESSAGE)]


async def test_redelivery_after_crash_reruns(pipeline):
    # A crash mid-job leaves the row in_progress and the message undeleted.
    pipeline.stored["14"] = IngestionJob("14", "https://github.com/x/y", JobStatus.IN_PROGRESS)

    await worker.handle_ingestion_job(_job_message())

    assert pipeline.runs == 1
    assert pipeline.stored["14"].status is JobStatus.READY
