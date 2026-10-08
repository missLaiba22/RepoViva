"""HTTP client for Evaluation Service's report endpoints (decision 049).

The sender side of the Core API → Evaluation Service contract: the
report trigger after an interview ends, and the report read behind
GET /v1/interviews/{id}/report. Kept out of the router and the service
layer, like ingestion_client.py.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

import httpx

from core_api.config import get_settings
from core_api.security.hmac_auth import sign

logger = logging.getLogger(__name__)

# Both endpoints only touch one row and return; generation itself runs in
# Evaluation's background. Short, so a hung Evaluation can't stall a
# user's request for long.
_TIMEOUT_SECONDS = 5.0

ReportOutcome = Literal["completed", "interrupted"]


class EvaluationServiceError(Exception):
    """Evaluation Service couldn't be reached or answered with an error.

    Wraps network errors and unexpected status codes alike.
    """


def _base_url() -> str:
    return get_settings().evaluation_service_base_url.rstrip("/")


def trigger_report(
    *,
    interview_id: int,
    repository_id: int,
    outcome: ReportOutcome,
    transport: httpx.BaseTransport | None = None,
) -> None:
    """Ask Evaluation Service to generate the interview's report.

    Fire-and-forget: Evaluation answers 202 and does the work in the
    background. Safe to repeat — a report that is generating or ready is
    left alone, a failed one is regenerated. Raises EvaluationServiceError.
    """
    settings = get_settings()
    body_bytes = json.dumps(
        {"interview_id": interview_id, "repository_id": repository_id, "outcome": outcome},
        separators=(",", ":"),
    ).encode()
    headers = {"Content-Type": "application/json"}
    headers.update(sign(body=body_bytes, secret=settings.internal_hmac_secret).as_dict())

    try:
        with httpx.Client(timeout=_TIMEOUT_SECONDS, transport=transport) as client:
            response = client.post(
                f"{_base_url()}/internal/v1/reports", content=body_bytes, headers=headers
            )
    except httpx.HTTPError as exc:
        raise EvaluationServiceError(f"could not reach Evaluation Service: {exc}") from exc

    if response.status_code >= 300:
        raise EvaluationServiceError(
            f"Evaluation Service returned {response.status_code}: {response.text[:200]}"
        )


def trigger_report_logged(*, interview_id: int, repository_id: int, outcome: ReportOutcome) -> None:
    """trigger_report for a background task: logs a failure instead of raising.

    A lost trigger only delays the report: the next read of it sends the
    trigger again (lazy re-trigger, decision 049).
    """
    try:
        trigger_report(interview_id=interview_id, repository_id=repository_id, outcome=outcome)
    except EvaluationServiceError:
        logger.warning(
            "report trigger for interview %d failed; it will be re-sent when the report is read",
            interview_id,
            exc_info=True,
        )


def get_report(
    interview_id: int, *, transport: httpx.BaseTransport | None = None
) -> dict | None:
    """The report as Evaluation Service holds it, or None if there is none.

    Raises EvaluationServiceError on anything other than 200 or 404.
    """
    settings = get_settings()
    # A GET has no body, so the signature covers the empty byte string.
    headers = sign(body=b"", secret=settings.internal_hmac_secret).as_dict()

    try:
        with httpx.Client(timeout=_TIMEOUT_SECONDS, transport=transport) as client:
            response = client.get(f"{_base_url()}/internal/v1/reports/{interview_id}", headers=headers)
    except httpx.HTTPError as exc:
        raise EvaluationServiceError(f"could not reach Evaluation Service: {exc}") from exc

    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise EvaluationServiceError(
            f"Evaluation Service returned {response.status_code}: {response.text[:200]}"
        )
    return response.json()
