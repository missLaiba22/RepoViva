"""The `interview.ended` event Voice publishes (decision 057)."""

import pytest
from repoviva_common.messaging import MessagingError

from voice_service.clients import events
from voice_service.clients.events import InterviewEventPublisher


@pytest.fixture
def published(monkeypatch):
    calls: list[tuple] = []

    def fake_publish(bus, source, type, data):
        calls.append((bus, source, type, data))
        if len(calls) == 1 and data.get("error_message") == "fail once":
            raise MessagingError("throttled")

    monkeypatch.setattr(events, "publish_event", fake_publish)
    return calls


async def test_interview_ended_contract(published):
    await InterviewEventPublisher("repoviva").interview_ended(
        interview_id=7, repository_id=15, outcome="interrupted", error_message="socket closed",
    )

    assert published == [(
        "repoviva", "repoviva.voice-service", "interview.ended",
        {"interview_id": 7, "repository_id": 15, "outcome": "interrupted",
         "error_message": "socket closed"},
    )]


async def test_publish_is_retried(published):
    await InterviewEventPublisher("repoviva", retry_delays_s=(0.0,)).interview_ended(
        interview_id=7, repository_id=15, outcome="completed", error_message="fail once",
    )

    assert len(published) == 2
