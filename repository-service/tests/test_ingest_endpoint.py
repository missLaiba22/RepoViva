# repository-service/tests/test_ingest_endpoint.py
"""Endpoint-level test for POST /internal/v1/repositories/{id}/ingest.

We call the handler function directly rather than going through TestClient.
Two reasons:

- TestClient's handling of background-task execution and mocking varies
  across Starlette/httpx/anyio versions; going through the client made
  earlier attempts non-deterministic.
- The router's responsibility here is exactly "return 202 and schedule
  run_ingestion with the right args." That is directly observable by
  inspecting the BackgroundTasks object we pass in — no client needed.

HMAC verification is not exercised here — it's covered by the hmac_auth
tests. Calling the handler function directly bypasses dependency
resolution entirely, which is what we want for a unit-level check.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import BackgroundTasks

from repository_service.config import Settings
from repository_service.ingestion.orchestrator import run_ingestion
from repository_service.internal.router import IngestTriggerBody, ingest_trigger


def _fake_settings() -> Settings:
    return Settings(
        env="test",
        core_api_base_url="http://core-api.test",
        internal_hmac_secret="unused-in-this-test",
        workspace_root=Path("/tmp/repoviva-test-workspace"),
    )


# repository-service/tests/test_ingest_endpoint.py

# 1. Change the function signature:
async def test_ingest_schedules_orchestrator_with_correct_args() -> None:
    background_tasks = BackgroundTasks()
    body = IngestTriggerBody(github_url="https://github.com/example/repo.git")

    # 2. Await the handler:
    result = await ingest_trigger(
        repository_id=42,
        body=body,
        background_tasks=background_tasks,
        settings=_fake_settings(),
    )

    # ... rest of assertions unchanged

    # 1. Response shape the router promises to Core API.
    assert result == {"status": "accepted", "repository_id": "42"}

    # 2. Exactly one task was scheduled to run after the response.
    assert len(background_tasks.tasks) == 1
    scheduled = background_tasks.tasks[0]

    # 3. It's the orchestrator, called with the request payload plus
    #    the workspace_root from settings. Starlette's BackgroundTask
    #    stores these three attributes directly.
    assert scheduled.func is run_ingestion
    assert scheduled.args == ()
    assert scheduled.kwargs == {
        "repository_id": "42",
        "github_url": "https://github.com/example/repo.git",
        "workspace_root": Path("/tmp/repoviva-test-workspace"),
    }