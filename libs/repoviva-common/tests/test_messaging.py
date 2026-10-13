import json

import pytest

from repoviva_common import messaging
from repoviva_common.messaging import (
    Message,
    MessagingError,
    build_message,
    handle_one,
    publish_event,
    publish_event_with_retry,
    send_job,
)


class FakeSqs:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.deleted: list[str] = []

    def send_message(self, **kwargs) -> None:
        self.sent.append(kwargs)

    def delete_message(self, *, QueueUrl: str, ReceiptHandle: str) -> None:
        self.deleted.append(ReceiptHandle)

    def change_message_visibility(self, **kwargs) -> None:
        pass


@pytest.fixture
def sqs(monkeypatch) -> FakeSqs:
    fake = FakeSqs()
    monkeypatch.setattr(messaging, "_sqs", fake)
    return fake


def _received(message: Message) -> dict:
    return {"ReceiptHandle": "r1", "Body": message.model_dump_json()}


def test_send_job_envelope_shape(sqs):
    send_job("q", "ingestion.requested", {"repository_id": 7})

    body = json.loads(sqs.sent[0]["MessageBody"])
    assert set(body) == {"message_id", "type", "occurred_at", "request_id", "data"}
    assert body["type"] == "ingestion.requested"
    assert body["data"] == {"repository_id": 7}


async def test_message_deleted_after_handler_succeeds(sqs):
    seen: list[Message] = []

    async def handler(message: Message) -> None:
        seen.append(message)

    message = build_message("t", {"x": 1})
    assert await handle_one(sqs, "q", _received(message), handler)
    assert seen == [message]
    assert sqs.deleted == ["r1"]


async def test_message_kept_when_handler_raises(sqs):
    async def handler(message: Message) -> None:
        raise RuntimeError("boom")

    assert not await handle_one(sqs, "q", _received(build_message("t", {})), handler)
    assert sqs.deleted == []


async def test_malformed_message_kept_for_dlq(sqs):
    async def handler(message: Message) -> None:
        raise AssertionError("must not run")

    assert not await handle_one(sqs, "q", {"ReceiptHandle": "r1", "Body": "{}"}, handler)
    assert sqs.deleted == []


class FakeEvents:
    def __init__(self, failed: int = 0) -> None:
        self.entries: list[dict] = []
        self.failed = failed

    def put_events(self, *, Entries: list[dict]) -> dict:
        self.entries.extend(Entries)
        return {"FailedEntryCount": self.failed, "Entries": [{"ErrorCode": "x"}]}


def test_publish_event_puts_envelope_as_detail(monkeypatch):
    events = FakeEvents()
    monkeypatch.setattr(messaging, "_events", events)

    publish_event("repoviva", "repoviva.voice-service", "interview.ended", {"interview_id": 3})

    entry = events.entries[0]
    assert (entry["EventBusName"], entry["Source"], entry["DetailType"]) == (
        "repoviva", "repoviva.voice-service", "interview.ended",
    )
    assert Message.model_validate_json(entry["Detail"]).data == {"interview_id": 3}


def test_publish_event_raises_on_failed_entry(monkeypatch):
    monkeypatch.setattr(messaging, "_events", FakeEvents(failed=1))

    with pytest.raises(MessagingError):
        publish_event("repoviva", "s", "t", {})


async def test_publish_with_retry_retries_then_succeeds(monkeypatch):
    calls = []

    def flaky(bus, source, type, data):
        calls.append(type)
        if len(calls) == 1:
            raise MessagingError("throttled")

    monkeypatch.setattr(messaging, "publish_event", flaky)

    assert await publish_event_with_retry("b", "s", "t", {}, retry_delays=(0.0,))
    assert len(calls) == 2


async def test_publish_with_retry_gives_up_without_raising(monkeypatch):
    def down(*args):
        raise MessagingError("down")

    monkeypatch.setattr(messaging, "publish_event", down)

    assert not await publish_event_with_retry("b", "s", "t", {}, retry_delays=(0.0,))
