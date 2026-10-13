"""The `interview.ended` event Voice publishes (decision 057)."""

from voice_service.clients import events
from voice_service.clients.events import InterviewEventPublisher


async def test_interview_ended_contract(monkeypatch):
    published: list[tuple] = []

    async def fake_publish(bus, source, type, data):
        published.append((bus, source, type, data))
        return True

    monkeypatch.setattr(events, "publish_event_with_retry", fake_publish)

    await InterviewEventPublisher("repoviva").interview_ended(
        interview_id=7, repository_id=15, outcome="interrupted", error_message="socket closed",
    )

    assert published == [(
        "repoviva", "repoviva.voice-service", "interview.ended",
        {"interview_id": 7, "repository_id": 15, "outcome": "interrupted",
         "error_message": "socket closed"},
    )]
