"""Core API's side of the Voice Service planning contract (decisions 052, 057).

Planning starts with a `plan.requested` job on SQS; its status is read
over HTTP, because the live page needs the answer now.
"""

from __future__ import annotations

from typing import Literal

import httpx
from repoviva_common.hmac_auth import sign
from repoviva_common.http import get_sync_client
from repoviva_common.messaging import MessagingError, send_job

from core_api.config import get_settings

PLAN_REQUESTED = "plan.requested"

# The status read touches one document. Short, so the polling live page
# never waits long on a hung Voice Service.
_TIMEOUT_SECONDS = 5.0

PlanStatus = Literal["generating", "ready", "failed"]


class VoiceServiceError(Exception):
    """The job couldn't be sent, or Voice Service couldn't be read."""


def request_plan(*, interview_id: int, repository_id: int) -> None:
    """Send a `plan.requested` job. Safe to repeat: a ready plan is left alone."""
    try:
        send_job(
            get_settings().planning_jobs_queue_url,
            PLAN_REQUESTED,
            {"interview_id": interview_id, "repository_id": repository_id},
        )
    except MessagingError as exc:
        raise VoiceServiceError(str(exc)) from exc


def get_plan_status(interview_id: int, *, http: httpx.Client | None = None) -> dict | None:
    """The plan's status as Voice Service holds it, or None if planning never started."""
    settings = get_settings()
    # A GET has no body, so the signature covers the empty byte string.
    headers = sign(body=b"", secret=settings.internal_hmac_secret)
    try:
        response = (http or get_sync_client()).get(
            f"{settings.voice_service_base_url.rstrip('/')}"
            f"/internal/v1/interviews/{interview_id}/plan",
            headers=headers,
            timeout=_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise VoiceServiceError(f"could not reach Voice Service: {exc}") from exc

    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise VoiceServiceError(
            f"Voice Service returned {response.status_code}: {response.text[:200]}"
        )
    return response.json()
