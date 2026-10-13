"""The ingestion status events Repository Service publishes (decision 057)."""

from repository_service.clients import events
from repository_service.clients.events import IngestionEventPublisher


async def test_ingestion_event_contract(monkeypatch):
    published: list[tuple] = []

    async def fake_publish(bus, source, type, data):
        published.append((bus, source, type, data))
        return True

    monkeypatch.setattr(events, "publish_event_with_retry", fake_publish)

    await IngestionEventPublisher("repoviva").emit_event(
        "14", "ingestion.failed", error_message="fetch failed",
    )

    assert published == [(
        "repoviva", "repoviva.repository-service", "ingestion.failed",
        {"repository_id": 14, "error_message": "fetch failed"},
    )]
