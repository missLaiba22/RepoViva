"""Grader sanity eval: does grading rank known-good answers above known-bad ones?

Usage (from evaluation-service/, Repository Service running, GROQ_API_KEY in .env):

    uv run python evals/grader_sanity.py evals/golden/grader_sanity_v1.json [--runs 2] [--repo URL]

Each case is a real interview question with three hand-written answers:
strong, vague and wrong. Every answer is graded `--runs` times through the
production path (RepositoryClient for the chunks, grade_turn for the
grade), with no previous exchange, so each answer is judged on its own.

Checks, per case and run (decision 050):
- order   — correctness: strong > vague and strong > wrong
- strong  — strong scores >= 4
- wrong   — wrong scores <= 2
- names   — the wrong answer's gaps mention its actual mistake
            (any of the case's `wrong_mistake_keywords`)

Also counts key points phrased as advice ("should ..."): key points must
say what the code does, not what it ought to do (decision 050).

Writes every grade to evals/results/ for reading by eye. Golden sets are
data: never edit answers or keywords after seeing results; add a new
version instead.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from evaluation_service.clients.repository import RepositoryClient
from evaluation_service.clients.voice import Turn
from evaluation_service.config import get_settings
from evaluation_service.grading.grader import grade_turn
from evaluation_service.grading.llm import get_llm
from evaluation_service.grading.prompts import PROMPT_VERSION

_RESULTS_DIR = Path(__file__).resolve().parent / "results"
KINDS = ("strong", "vague", "wrong")
_ADVICE = re.compile(r"\bshould\b", re.IGNORECASE)


async def grade_case(case: dict, repo: RepositoryClient, repository_id: int, llm, runs: int):
    found = await repo.get_chunks(repository_id, case["chunk_ids"])
    chunks = [found[i] for i in case["chunk_ids"] if i in found]
    results = []
    for run in range(1, runs + 1):
        grades = {}
        for kind in KINDS:
            turn = Turn(
                seq=1,
                question_text=case["question"],
                answer_text=case["answers"][kind],
                status="answered",
                retrieved_chunk_ids=case["chunk_ids"],
            )
            grade = await grade_turn(llm, turn, None, chunks)
            grades[kind] = grade.model_dump() if grade else None
        results.append({"run": run, "grades": grades})
    return results


def advice_key_points(grades: dict) -> tuple[int, int]:
    """(key points phrased as advice, all key points) across one run's grades."""
    points = [kp["point"] for g in grades.values() if g for kp in g["key_points"]]
    return sum(bool(_ADVICE.search(p)) for p in points), len(points)


def check(case: dict, grades: dict) -> dict[str, bool]:
    if any(g is None for g in grades.values()):
        return {"graded": False}
    score = {k: grades[k]["correctness"]["score"] for k in KINDS}
    gaps = " ".join(grades["wrong"]["gaps"] + [grades["wrong"]["correctness"]["justification"]])
    return {
        "order": score["strong"] > score["vague"] and score["strong"] > score["wrong"],
        "strong": score["strong"] >= 4,
        "wrong": score["wrong"] <= 2,
        "names": any(k.lower() in gaps.lower() for k in case["wrong_mistake_keywords"]),
    }


async def run_eval(golden: dict, repo_url: str | None, runs: int) -> list[dict]:
    settings = get_settings()
    repo = RepositoryClient(
        repo_url or settings.repository_service_base_url, settings.internal_hmac_secret
    )
    llm = get_llm()
    out = []
    for case in golden["cases"]:
        out.append({"case": case["id"], "runs": await grade_case(case, repo, golden["repository_id"], llm, runs)})
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("golden")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--repo", help="Repository Service base URL (default from .env)")
    args = parser.parse_args()

    golden = json.loads(Path(args.golden).read_text(encoding="utf-8"))
    results = asyncio.run(run_eval(golden, args.repo, args.runs))
    cases = {c["id"]: c for c in golden["cases"]}

    model = get_settings().eval_llm_model
    print(f"{golden['name']} · {model} · prompt {PROMPT_VERSION} · {args.runs} run(s)\n")
    print(f"{'case':24} run  strong vague wrong  order strong wrong names")
    passed = total = advice = points = 0
    for r in results:
        for run in r["runs"]:
            g = run["grades"]
            checks = check(cases[r["case"]], g)
            scores = "  ".join(
                f"{g[k]['correctness']['score'] if g[k] else '-':>5}" for k in KINDS
            )
            marks = "  ".join(f"{'ok' if checks.get(c) else 'FAIL':>5}" for c in ("order", "strong", "wrong", "names"))
            print(f"{r['case']:24} {run['run']:>3}  {scores}  {marks}")
            passed += sum(checks.values())
            total += 4
            a, n = advice_key_points(g)
            advice += a
            points += n
    print(f"\n{passed}/{total} checks passed")
    print(f'{advice}/{points} key points phrased as advice ("should")')

    _RESULTS_DIR.mkdir(exist_ok=True)
    out = _RESULTS_DIR / f"{datetime.now(UTC).astimezone().date()}_{golden['name']}_{PROMPT_VERSION}.json"
    out.write_text(
        json.dumps({"model": model, "prompt_version": PROMPT_VERSION, "results": results}, indent=2),
        encoding="utf-8",
    )
    print(f"grades written to {out.relative_to(_RESULTS_DIR.parent.parent)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.WARNING)
    main()
