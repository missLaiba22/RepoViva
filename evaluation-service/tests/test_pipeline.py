"""generate_report end to end with fake Voice, Repository and LLM."""

import json

from evaluation_service.grading.prompts import PROMPT_VERSION
from evaluation_service.pipeline import generate_report
from tests.fakes import FakeRepository, FakeVoice, chunk, grade, make_llm, turn

NOTES = {
    "strengths": ["You reason about failure cases."],
    "improvements": ["Name the mechanism, not just the outcome."],
    "files_to_revisit": [{"file": "orders/service.py", "reason": "locking"}],
}


async def run(turns, chunks, *script, partial=False):
    llm, completion = make_llm(*script)
    repository = FakeRepository(chunks)
    report = await generate_report(
        interview_id=7,
        repository_id=15,
        partial=partial,
        voice=FakeVoice(turns),
        repository=repository,
        llm=llm,
    )
    return report, completion, repository


async def test_full_interview():
    turns = [turn(1, chunk_ids=[1, 2]), turn(2, chunk_ids=[2, 3])]
    chunks = [chunk(1), chunk(2), chunk(3, filename="payments/webhook.py")]

    report, completion, repository = await run(
        turns,
        chunks,
        grade(correctness=4, clarity=3),
        grade(correctness=2, clarity=5, key_points=[{"point": "p", "chunk_ids": [3]}], evidence=[3]),
        NOTES,
    )

    # One fetch with every chunk id, de-duplicated.
    assert repository.requested == [[1, 2, 3]]
    assert len(completion.calls) == 3  # two turns + summary
    assert report.partial is False
    assert report.model == "test-model"
    assert report.prompt_version == PROMPT_VERSION

    first, second = report.turn_evaluations
    assert first["status"] == "graded"
    assert first["key_points"][0]["sources"] == [
        {"chunk_id": 1, "filename": "orders/service.py", "start_line": 1, "end_line": 10}
    ]
    assert second["evidence"][0]["filename"] == "payments/webhook.py"
    assert [s["chunk_id"] for s in second["sources"]] == [2, 3]

    assert report.summary["average_correctness"] == 3.0
    assert report.summary["average_clarity"] == 4.0
    assert report.summary["improvements"] == NOTES["improvements"]
    assert report.summary["files_to_revisit"] == NOTES["files_to_revisit"]

    # Turn 2's prompt carries turn 1 as context.
    assert "Previous exchange" in completion.calls[1]["messages"][1]["content"]
    # The whole report is JSON-serialisable, as the JSONB columns need.
    json.dumps(report.turn_evaluations)
    json.dumps(report.summary)


async def test_interrupted_interview_lists_unanswered_turns():
    turns = [turn(1, chunk_ids=[1]), turn(2, answer=None, chunk_ids=[9])]

    report, _, repository = await run(turns, [chunk(1)], grade(), NOTES, partial=True)

    assert report.partial is True
    assert repository.requested == [[1]]  # unanswered turn's chunks aren't fetched
    assert report.turn_evaluations[1] == {
        "seq": 2,
        "question": "Question 2?",
        "answer": None,
        "status": "not_answered",
    }
    assert report.summary["turns_asked"] == 2
    assert report.summary["turns_answered"] == 1
    assert report.summary["average_correctness"] == 4.0


async def test_blank_transcript_counts_as_not_answered():
    report, completion, _ = await run([turn(1, answer="   ")], [chunk(1)])

    assert report.turn_evaluations[0]["status"] == "not_answered"
    assert completion.calls == []


async def test_no_answers_still_gives_a_report_without_scores_or_llm_calls():
    report, completion, repository = await run([turn(1, answer=None)], [], partial=True)

    assert completion.calls == []
    assert repository.requested == []
    assert report.summary["average_correctness"] is None
    assert report.summary["strengths"] == []


async def test_unusable_grade_marks_only_that_turn():
    turns = [turn(1, chunk_ids=[1]), turn(2, chunk_ids=[1])]

    report, _, _ = await run(turns, [chunk(1)], "bad", "bad again", grade(), NOTES)

    assert report.turn_evaluations[0]["status"] == "not_graded"
    assert report.turn_evaluations[1]["status"] == "graded"
    assert report.summary["turns_graded"] == 1


async def test_summary_failure_keeps_the_numbers():
    report, _, _ = await run([turn(1, chunk_ids=[1])], [chunk(1)], grade(), "x", "y")

    assert report.summary["average_correctness"] == 4.0
    assert report.summary["strengths"] == []


async def test_missing_chunks_grade_with_what_is_left():
    report, completion, _ = await run([turn(1, chunk_ids=[1, 2])], [chunk(1)], grade(), NOTES)

    assert [s["chunk_id"] for s in report.turn_evaluations[0]["sources"]] == [1]
    assert "chunk 2:" not in completion.calls[0]["messages"][1]["content"]
