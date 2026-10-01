from datetime import datetime, timezone
from types import SimpleNamespace

from core_api.interviews.schemas import InterviewCreatedResponse, InterviewResponse


def test_created_response_builds_from_interview_plus_token():
    now = datetime.now(timezone.utc)
    interview = SimpleNamespace(
        id=1, repository_id=15, status="created", error_message=None,
        session_token_consumed_at=None, ended_at=None,
        created_at=now, updated_at=now,
        session_token_hash="must-never-appear",
    )
    base = InterviewResponse.model_validate(interview)
    body = InterviewCreatedResponse(
        **base.model_dump(),
        session_token="raw-token",
        session_token_expires_at=now,
    ).model_dump()

    assert body["session_token"] == "raw-token"
    assert "started_at" in body
    assert "session_token_hash" not in body
    assert "owner_user_id" not in body