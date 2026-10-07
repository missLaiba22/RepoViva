"""Grounding rules and summary numbers (decision 050)."""

from evaluation_service.grading.grader import enforce_grounding, grade_turn, name_chunk_refs
from evaluation_service.grading.models import TurnGrade
from evaluation_service.grading.prompts import build_grade_prompt
from evaluation_service.grading.summary import compute_scores, write_notes
from tests.fakes import chunk, grade, make_llm, turn


def test_grounding_drops_unknown_ids_and_unsupported_key_points():
    raw = TurnGrade.model_validate(
        grade(
            key_points=[
                {"point": "kept, one id dropped", "chunk_ids": [1, 99]},
                {"point": "dropped, nothing valid", "chunk_ids": [42]},
                {"point": "dropped, no citation", "chunk_ids": []},
            ],
            evidence=[2, 77],
        )
    )

    cleaned, dropped = enforce_grounding(raw, allowed_ids={1, 2})

    assert [kp.point for kp in cleaned.key_points] == ["kept, one id dropped"]
    assert cleaned.key_points[0].chunk_ids == [1]
    assert cleaned.evidence_chunk_ids == [2]
    assert dropped == 3  # 99, 42, 77


async def test_grade_turn_cites_only_chunks_it_was_shown():
    llm, completion = make_llm(grade(key_points=[{"point": "p", "chunk_ids": [5]}], evidence=[5]))

    result = await grade_turn(llm, turn(1, chunk_ids=[1]), None, [chunk(1)])

    assert result.key_points == []
    assert result.evidence_chunk_ids == []
    assert "chunk 1: orders/service.py:1-10" in completion.calls[0]["messages"][1]["content"]


async def test_grade_turn_returns_none_when_model_never_complies():
    llm, _ = make_llm("nope", "still nope")

    assert await grade_turn(llm, turn(1), None, [chunk(1)]) is None


def test_prompt_includes_previous_exchange_as_context():
    prompt = build_grade_prompt(turn(2, answer="Second."), turn(1, answer="First."), [])

    assert "Previous exchange (context only)" in prompt
    assert prompt.index("First.") < prompt.index("Answer to grade") < prompt.index("Second.")
    assert "No code excerpts" in prompt


def _graded(seq, correctness, clarity, filename="orders/service.py"):
    return {
        "seq": seq,
        "question": f"Q{seq}",
        "status": "graded",
        "correctness": {"score": correctness, "justification": "j"},
        "clarity": {"score": clarity, "justification": "j"},
        "strengths": [],
        "gaps": ["g"],
        "sources": [{"chunk_id": seq, "filename": filename, "start_line": 1, "end_line": 9}],
    }


def test_scores_average_graded_turns_only():
    evaluations = [
        _graded(1, 4, 3),
        _graded(2, 3, 4),
        {"seq": 3, "status": "not_graded", "sources": []},
        {"seq": 4, "status": "not_answered"},
    ]

    scores = compute_scores(evaluations)

    assert scores == {
        "average_correctness": 3.5,
        "average_clarity": 3.5,
        "turns_asked": 4,
        "turns_answered": 3,
        "turns_graded": 2,
    }


def test_scores_are_none_when_nothing_was_graded():
    scores = compute_scores([{"seq": 1, "status": "not_answered"}])

    assert scores["average_correctness"] is None
    assert scores["average_clarity"] is None
    assert scores["turns_answered"] == 0


async def test_notes_keep_only_files_behind_graded_turns():
    llm, _ = make_llm(
        {
            "strengths": ["s"],
            "improvements": ["i"],
            "files_to_revisit": [
                {"file": "orders/service.py", "reason": "locking"},
                {"file": "invented/file.py", "reason": "?"},
            ],
        }
    )

    notes = await write_notes(llm, [_graded(1, 2, 2)])

    assert [f.file for f in notes.files_to_revisit] == ["orders/service.py"]


async def test_notes_skip_the_llm_when_nothing_was_graded():
    llm, completion = make_llm()

    assert await write_notes(llm, [{"seq": 1, "status": "not_answered"}]) is None
    assert completion.calls == []


def test_chunk_refs_in_prose_become_file_and_line():
    chunks = {142: chunk(142), 493: chunk(493, filename="DECISIONS.md")}

    assert name_chunk_refs("as the comment says (chunk 142).", chunks) == (
        "as the comment says (orders/service.py:142)."
    )
    assert name_chunk_refs("see chunks 142 and 493", chunks) == (
        "see orders/service.py:142 and DECISIONS.md:493"
    )
    assert name_chunk_refs("Chunk 7 shows it", chunks) == "the code shows it"
    assert name_chunk_refs("no refs here", chunks) == "no refs here"


async def test_grade_turn_names_chunk_refs_everywhere():
    payload = grade(key_points=[{"point": "chunk 1 locks rows", "chunk_ids": [1]}])
    payload["correctness"]["justification"] = "matches chunk 1"
    payload["gaps"] = ["missed chunk 1"]
    llm, _ = make_llm(payload)

    result = await grade_turn(llm, turn(1, chunk_ids=[1]), None, [chunk(1)])

    assert result.correctness.justification == "matches orders/service.py:1"
    assert result.gaps == ["missed orders/service.py:1"]
    assert result.key_points[0].point == "orders/service.py:1 locks rows"
