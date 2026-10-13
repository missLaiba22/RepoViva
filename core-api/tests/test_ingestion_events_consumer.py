"""Core API's consumer of Repository Service's `ingestion.*` events (decision 057)."""

import contextlib

import pytest
from pydantic import ValidationError
from repoviva_common.messaging import build_message

from core_api import worker
from core_api.repositories import service as repositories_service


@pytest.fixture
def applied(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(worker, "SessionLocal", lambda: contextlib.nullcontext("db"))
    monkeypatch.setattr(
        worker.repositories_service,
        "apply_ingestion_event",
        lambda db, **kw: calls.append(kw) or object(),
    )
    return calls


def test_ingestion_event_contract():
    event = worker.IngestionEvent.model_validate({"repository_id": 14, "error_message": None})
    assert event.repository_id == 14
    with pytest.raises(ValidationError):
        worker.IngestionEvent.model_validate({"error_message": "x"})


def test_failed_event_applies_its_error(applied):
    worker.apply_ingestion_event(
        "ingestion.failed",
        worker.IngestionEvent(repository_id=14, error_message="fetch failed"),
    )

    assert applied == [
        {"repository_id": 14, "event_type": "ingestion.failed", "error_message": "fetch failed"}
    ]


def test_late_event_is_handled(monkeypatch):
    def terminal(db, **kw):
        raise repositories_service.IllegalTransitionError("already ready")

    monkeypatch.setattr(worker, "SessionLocal", lambda: contextlib.nullcontext("db"))
    monkeypatch.setattr(worker.repositories_service, "apply_ingestion_event", terminal)

    # Returns normally, so run_worker deletes the message.
    worker.apply_ingestion_event("ingestion.started", worker.IngestionEvent(repository_id=14))


def test_unknown_event_type_is_rejected():
    message = build_message("ingestion.paused", {"repository_id": 14})

    with pytest.raises(ValidationError):
        worker._IngestionMessageType(type=message.type)
