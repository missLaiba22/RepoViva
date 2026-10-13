"""Sends ingestion jobs to Repository Service over SQS (decision 057)."""

from __future__ import annotations

from repoviva_common.messaging import MessagingError, send_job

from core_api.config import get_settings

INGESTION_REQUESTED = "ingestion.requested"


class IngestionTriggerError(Exception):
    """The ingestion job could not be sent. The router marks the repository `failed`."""


def trigger_ingestion(*, repository_id: int, github_url: str) -> None:
    # github_url travels with the job: Repository Service doesn't store it.
    try:
        send_job(
            get_settings().ingestion_jobs_queue_url,
            INGESTION_REQUESTED,
            {"repository_id": repository_id, "github_url": github_url},
        )
    except MessagingError as exc:
        raise IngestionTriggerError(str(exc)) from exc
