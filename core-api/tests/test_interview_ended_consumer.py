"""Core API's consumer of `interview.ended` (decision 057)."""

import contextlib
import subprocess
import sys

import pytest
from pydantic import ValidationError
from repoviva_common.messaging import build_message

from core_api import worker
from core_api.interviews import service as interviews_service


@pytest.fixture
def ended(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(worker, "SessionLocal", lambda: contextlib.nullcontext("db"))
    monkeypatch.setattr(
        worker.interviews_service, "end_interview", lambda db, **kw: calls.append(kw) or object()
    )
    return calls


def _event(**data):
    return build_message(
        "interview.ended",
        {"interview_id": 7, "repository_id": 15, "outcome": "interrupted",
         "error_message": "client disconnected"} | data,
    )


def test_interview_ended_contract():
    with pytest.raises(ValidationError):
        worker.InterviewEnded.model_validate({"interview_id": 7, "outcome": "completed"})
    with pytest.raises(ValidationError):
        worker.InterviewEnded.model_validate(_event(outcome="active").data)


def test_event_ends_the_interview(ended):
    worker.end_interview(worker.InterviewEnded.model_validate(_event().data))

    assert ended == [
        {"interview_id": 7, "outcome": "interrupted", "error_message": "client disconnected"}
    ]


def test_duplicate_end_event_is_handled(monkeypatch):
    def already_ended(db, **kw):
        raise interviews_service.IllegalTransitionError("already completed")

    monkeypatch.setattr(worker, "SessionLocal", lambda: contextlib.nullcontext("db"))
    monkeypatch.setattr(worker.interviews_service, "end_interview", already_ended)

    # Returns normally, so run_worker deletes the message.
    worker.end_interview(worker.InterviewEnded.model_validate(_event().data))


def test_worker_loads_every_model_it_needs():
    # Regression: the worker failed every event with NoReferencedTableError.
    # A fresh process, since other tests import the app and all its models.
    code = (
        "from core_api import worker\n"
        "for fk in worker.interviews_service.Interview.__table__.foreign_keys: fk.column"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
