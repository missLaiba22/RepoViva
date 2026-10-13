import pytest

from core_api.interviews.models import InterviewStatus
from core_api.interviews.service import IllegalTransitionError, target_status_for


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        ("completed", InterviewStatus.COMPLETED),
        ("interrupted", InterviewStatus.INTERRUPTED),
    ],
)
def test_active_interview_can_end(outcome, expected):
    assert target_status_for("active", outcome) is expected


@pytest.mark.parametrize("current", ["created", "completed", "interrupted"])
def test_only_active_interviews_can_end(current):
    with pytest.raises(IllegalTransitionError):
        target_status_for(current, "completed")
