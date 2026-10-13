"""Ingestion job contract and idempotency under SQS redelivery (decision 057)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from repoviva_common.messaging import build_message

from repository_service import worker
from repository_service.ingestion import jobs, orchestrator
from repository_service.ingestion.jobs import IngestionJob, JobStatus


@pytest.fixture
def pipeline(monkeypatch):
    """Fakes the job store, Core API and fetch/index. Returns the recorded calls."""
    calls = SimpleNamespace(stored={}, events=[], runs=0)

    async def fake_claim(_pool, *, repository_id, github_url):
        calls.stored.setdefault(
            repository_id, IngestionJob(repository_id, github_url, JobStatus.IN_PROGRESS),
        )

    async def fake_get(_pool, repository_id):
        return calls.stored.get(repository_id)

    async def fake_set_status(_pool, repository_id, status):
        job = calls.stored[repository_id]
        calls.stored[repository_id] = IngestionJob(job.repository_id, job.github_url, status)

    class FakeClient:
        async def emit_event(self, repository_id, event, data=None):
            calls.events.append(event)

    async def fake_ingest(_job):
        calls.runs += 1

    monkeypatch.setattr(jobs, "claim", fake_claim)
    monkeypatch.setattr(jobs, "get", fake_get)
    monkeypatch.setattr(jobs, "set_status", fake_set_status)
    monkeypatch.setattr(orchestrator, "get_db_pool", lambda: None)
    monkeypatch.setattr(worker, "get_db_pool", lambda: None)
    monkeypatch.setattr(orchestrator, "get_core_api_client", lambda: FakeClient())
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
    assert pipeline.events == ["ingestion.started", "ingestion.completed"]


async def test_duplicate_message_for_finished_job_does_nothing(pipeline):
    await worker.handle_ingestion_job(_job_message())
    await worker.handle_ingestion_job(_job_message())

    assert pipeline.runs == 1


async def test_redelivery_after_crash_reruns(pipeline):
    # A crash mid-job leaves the row in_progress and the message undeleted.
    pipeline.stored["14"] = IngestionJob("14", "https://github.com/x/y", JobStatus.IN_PROGRESS)

    await worker.handle_ingestion_job(_job_message())

    assert pipeline.runs == 1
    assert pipeline.stored["14"].status is JobStatus.READY
