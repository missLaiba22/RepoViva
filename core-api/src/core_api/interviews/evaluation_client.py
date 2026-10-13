"""Core API's side of the Evaluation Service contract (decisions 049, 057).

The report read behind GET /v1/interviews/{id}/report (HTTP), and the
recovery/retry trigger (an SQS job). Kept out of the router and the
service layer, like ingestion_client.py.
"""

from __future__ import annotations

from typing import Literal

import httpx
from repoviva_common.hmac_auth import sign
from repoviva_common.http import get_sync_client
from repoviva_common.messaging import MessagingError, send_job

from core_api.config import get_settings


# The read touches one row. Short, so a hung Evaluation can't stall a
# user's request for long.
_TIMEOUT_SECONDS = 5.0

ReportOutcome = Literal["completed", "interrupted"]
REPORT_REQUESTED = "report.requested"


class EvaluationServiceError(Exception):
    """Evaluation Service couldn't be reached or answered with an error.

    Wraps network errors and unexpected status codes alike.
    """


def _base_url() -> str:
    return get_settings().evaluation_service_base_url.rstrip("/")


def trigger_report(*, interview_id: int, repository_id: int, outcome: ReportOutcome) -> None:
    """Send a `report.requested` job for recovery or retry (decision 057).

    The normal path needs no trigger: Evaluation consumes `interview.ended`.
    Safe to repeat — a ready report is left alone, a failed or unfinished
    one is regenerated. Raises EvaluationServiceError if the job can't be sent.
    """
    try:
        send_job(
            get_settings().report_jobs_queue_url,
            REPORT_REQUESTED,
            {"interview_id": interview_id, "repository_id": repository_id, "outcome": outcome},
        )
    except MessagingError as exc:
        raise EvaluationServiceError(str(exc)) from exc


def get_report(interview_id: int, *, http: httpx.Client | None = None) -> dict | None:
    """The report as Evaluation Service holds it, or None if there is none.

    Raises EvaluationServiceError on anything other than 200 or 404.
    """
    settings = get_settings()
    # A GET has no body, so the signature covers the empty byte string.
    headers = sign(body=b"", secret=settings.internal_hmac_secret)

    try:
        response = (http or get_sync_client()).get(
            f"{_base_url()}/internal/v1/reports/{interview_id}",
            headers=headers,
            timeout=_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise EvaluationServiceError(f"could not reach Evaluation Service: {exc}") from exc

    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise EvaluationServiceError(
            f"Evaluation Service returned {response.status_code}: {response.text[:200]}"
        )
    return response.json()
