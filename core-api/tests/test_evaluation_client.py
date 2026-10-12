"""evaluation_client against a mocked HTTP client: what it signs, sends and raises."""

import json

import httpx
import pytest
from repoviva_common.hmac_auth import SIGNATURE_HEADER, TIMESTAMP_HEADER, verify

from core_api.config import get_settings
from core_api.interviews import evaluation_client
from core_api.interviews.evaluation_client import (
    EvaluationServiceError,
    get_report,
    trigger_report,
    trigger_report_logged,
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


def test_trigger_posts_signed_body():
    seen = []

    trigger_report(
        interview_id=7, repository_id=15, outcome="interrupted", http=mock_http(202, seen=seen)
    )

    (request,) = seen
    assert request.method == "POST"
    assert request.url.path == "/internal/v1/reports"
    assert json.loads(request.content) == {
        "interview_id": 7,
        "repository_id": 15,
        "outcome": "interrupted",
    }
    assert_signed(request)


def test_trigger_raises_on_error_status():
    with pytest.raises(EvaluationServiceError, match="500"):
        trigger_report(interview_id=7, repository_id=15, outcome="completed", http=mock_http(500))


def test_trigger_raises_when_unreachable():
    def refuse(request):
        raise httpx.ConnectError("connection refused")

    with pytest.raises(EvaluationServiceError, match="could not reach"):
        trigger_report(
            interview_id=7,
            repository_id=15,
            outcome="completed",
            http=httpx.Client(transport=httpx.MockTransport(refuse)),
        )


def test_logged_trigger_swallows_failure(monkeypatch, caplog):
    def fail(**kwargs):
        raise EvaluationServiceError("down")

    monkeypatch.setattr(evaluation_client, "trigger_report", fail)

    trigger_report_logged(interview_id=7, repository_id=15, outcome="completed")

    assert "interview 7 failed" in caplog.text


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
