"""Generate one interview's report and print it, without storing anything.

For checking grading by eye. Needs Voice Service and Repository Service
running, and a GROQ_API_KEY in .env.

Usage:
    uv run python scripts/eval_report.py <interview_id> <repository_id> [--partial] [--json out.json]
    uv run python scripts/eval_report.py 7 15 --voice http://localhost:8102 --repo http://localhost:8101
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import asdict

from evaluation_service.clients.repository import RepositoryClient
from evaluation_service.clients.voice import VoiceClient
from evaluation_service.config import get_settings
from evaluation_service.grading.llm import get_llm
from evaluation_service.pipeline import generate_report


def print_report(report) -> None:
    s = report.summary
    print(f"\nmodel {report.model} · prompt {report.prompt_version} · partial={report.partial}")
    print(
        f"correctness {s['average_correctness']} · clarity {s['average_clarity']} · "
        f"graded {s['turns_graded']}/{s['turns_answered']} answered of {s['turns_asked']} asked"
    )
    for e in report.turn_evaluations:
        print(f"\n── Q{e['seq']} [{e['status']}] {e['question']}")
        if e["answer"]:
            print(f"   A: {e['answer'][:300]}{'…' if len(e['answer']) > 300 else ''}")
        if e["status"] != "graded":
            continue
        for dim in ("correctness", "clarity"):
            print(f"   {dim} {e[dim]['score']}/5: {e[dim]['justification']}")
        for label in ("strengths", "gaps"):
            for item in e[label]:
                print(f"   {label[:-1]}: {item}")
        for kp in e["key_points"]:
            refs = ", ".join(f"{r['filename']}:{r['start_line']}" for r in kp["sources"])
            print(f"   key point: {kp['point']}  [{refs}]")
    print("\n── Summary")
    for label in ("strengths", "improvements"):
        for item in s[label]:
            print(f"   {label}: {item}")
    for f in s["files_to_revisit"]:
        print(f"   revisit {f['file']}: {f['reason']}")


async def generate(args: argparse.Namespace):
    settings = get_settings()
    return await generate_report(
        interview_id=args.interview_id,
        repository_id=args.repository_id,
        partial=args.partial,
        voice=VoiceClient(args.voice or settings.voice_service_base_url, settings.internal_hmac_secret),
        repository=RepositoryClient(
            args.repo or settings.repository_service_base_url, settings.internal_hmac_secret
        ),
        llm=get_llm(),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("interview_id", type=int)
    parser.add_argument("repository_id", type=int)
    parser.add_argument("--partial", action="store_true")
    parser.add_argument("--voice", help="Voice Service base URL (default from .env)")
    parser.add_argument("--repo", help="Repository Service base URL (default from .env)")
    parser.add_argument("--json", help="also write the report to this file")
    args = parser.parse_args()

    started = time.monotonic()
    report = asyncio.run(generate(args))
    elapsed = time.monotonic() - started
    # Saved before printing, so a console error can't lose a minute of grading.
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(asdict(report), f, indent=2, ensure_ascii=False)
    print_report(report)
    print(f"\ngenerated in {elapsed:.0f} s")


if __name__ == "__main__":
    # Windows consoles default to cp1252, which can't print the report's dashes.
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    for noisy in ("httpx", "LiteLLM"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    main()
