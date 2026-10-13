"""evaluation_client: the report job it sends, and the signed report read."""


import httpx
import pytest
from repoviva_common.hmac_auth import SIGNATURE_HEADER, TIMESTAMP_HEADER, verify
from repoviva_common.messaging import MessagingError

from core_api.config import get_settings
from core_api.interviews import evaluation_client
from core_api.interviews.evaluation_client import (
    EvaluationServiceError,
    get_report,
    trigger_report,
)


def mock_http(status_code=200, json_body=None, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status_code, json=json_body if json_body is not None else {})

    return httpx.Client(transport=httpx.MockTransport(handler))


def assert_signed(request: httpx.Request) -> None:
    verify(
        body=request.content,
        timestamp_header=request.headers.get(TIMESTAMP_HEADER),
        signature_header=request.headers.get(SIGNATURE_HEADER),
        secret=get_settings().internal_hmac_secret,
    )


def test_trigger_sends_report_job(monkeypatch):
    sent = []
    monkeypatch.setattr(
        evaluation_client, "send_job", lambda queue, type, data: sent.append((queue, type, data))
    )

    trigger_report(interview_id=7, repository_id=15, outcome="interrupted")

    assert sent == [(
        get_settings().report_jobs_queue_url,
        "report.requested",
        {"interview_id": 7, "repository_id": 15, "outcome": "interrupted"},
    )]


def test_trigger_raises_when_job_not_sent(monkeypatch):
    def fail(*args):
        raise MessagingError("queue down")

    monkeypatch.setattr(evaluation_client, "send_job", fail)

    with pytest.raises(EvaluationServiceError, match="queue down"):
        trigger_report(interview_id=7, repository_id=15, outcome="completed")


def test_get_report_returns_json_and_signs_empty_body():
    seen = []
    report = {"interview_id": 7, "status": "ready"}

    assert get_report(7, http=mock_http(200, report, seen)) == report
    assert seen[0].url.path == "/internal/v1/reports/7"
    assert_signed(seen[0])


def test_get_report_404_is_none():
    assert get_report(7, http=mock_http(404)) is None


@pytest.mark.parametrize("code", [401, 500, 503])
def test_get_report_raises_on_other_status(code):
    with pytest.raises(EvaluationServiceError):
        get_report(7, http=mock_http(code))
