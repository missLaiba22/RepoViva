import pytest
from pydantic import ValidationError

from core_api.internal.schemas import InterviewEventBody
from core_api.interviews.models import InterviewStatus
from core_api.interviews.service import IllegalTransitionError, target_status_for


@pytest.mark.parametrize(
    ("event_type", "expected"),
    [
        ("interview.completed", InterviewStatus.COMPLETED),
        ("interview.interrupted", InterviewStatus.INTERRUPTED),
    ],
)
def test_active_interview_can_end(event_type, expected):
    assert target_status_for("active", event_type) is expected


@pytest.mark.parametrize("current", ["created", "completed", "interrupted"])
def test_only_active_interviews_can_end(current):
    with pytest.raises(IllegalTransitionError):
        target_status_for(current, "interview.completed")


def test_event_body_rejects_ingestion_event_types():
    with pytest.raises(ValidationError):
        InterviewEventBody(
            event_id="6f1c1f9e-4d4b-4c4a-9a43-3f0f6f3b2b11",
            event_type="ingestion.completed",
            occurred_at="2026-10-06T12:00:00Z",
        )
