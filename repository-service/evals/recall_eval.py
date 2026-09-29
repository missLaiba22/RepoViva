"""Retrieval recall eval: run a golden question set against indexed repositories.

Usage (from repository-service/, Postgres up, VOYAGE_API_KEY in .env):

    uv run python evals/recall_eval.py evals/golden/fastapi.json 14 [14-no-translations ...]

Each repository id is searched with the same query embeddings through the
production retrieval path (EMBEDDER + retrieval.search_chunks). Prints a
summary table and writes per-query top-k to evals/results/.

Metrics, per repository:
- recall@k  — share of queries with at least one relevant file in top-k
- strict    — same, but hits matching the golden set's `noise_pattern`
              (e.g. translated docs) do not count
- MRR       — mean reciprocal rank of the first relevant hit
- noise     — top-k slots taken by `noise_pattern` matches

Costs one Voyage embedding per query. Golden sets are data, not code:
never edit a set's queries or relevance lists after seeing results —
add a new set (or a new version) instead, so past numbers stay comparable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

_SERVICE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_SERVICE_DIR / ".env")

import asyncpg  # noqa: E402

from repository_service.config import get_settings  # noqa: E402
from repository_service.indexing.embedder import EMBEDDER  # noqa: E402
from repository_service.retrieval import search_chunks  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"


async def run(golden_path: Path, repos: list[str]) -> None:
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    k: int = golden["k"]
    noise = re.compile(golden["noise_pattern"]) if golden.get("noise_pattern") else None
    queries = golden["queries"]

    totals = {r: {"hit": 0, "strict": 0, "noise": 0, "rr": 0.0} for r in repos}
    report: list[str] = []

    pool = await asyncpg.create_pool(get_settings().database_url)
    try:
        for item in queries:
            patterns = item["relevant"]
            emb = await EMBEDDER.embed(item["query"])
            lines = [item["query"]]
            for repo in repos:
                rows = await search_chunks(
                    pool, repository_id=repo, query_embedding=emb,
                    top_k=k, filename_prefix=None, exclude_chunk_ids=[],
                )
                files = [r["filename"] for r in rows]
                rel = [any(re.match(p, f) for p in patterns) for f in files]
                is_noise = [bool(noise and noise.match(f)) for f in files]
                t = totals[repo]
                t["hit"] += any(rel)
                t["strict"] += any(ok and not n for ok, n in zip(rel, is_noise))
                t["noise"] += sum(is_noise)
                t["rr"] += next((1 / (i + 1) for i, ok in enumerate(rel) if ok), 0.0)
                lines.append(
                    f"  [{repo}] {'HIT ' if any(rel) else 'MISS'}  "
                    + ", ".join(("*" if ok else "") + f for f, ok in zip(files, rel))
                )
            report.append("\n".join(lines))
    finally:
        await pool.close()

    n = len(queries)
    summary = [
        f"golden set: {golden_path.name} ({golden['repository']} @ {golden.get('commit', '?')})",
        f"{n} queries, k={k}, run {date.today().isoformat()}",
        "",
        f"{'repository':<24} {'recall@k':>9} {'strict':>8} {'MRR':>6} {'noise slots':>14}",
    ]
    for repo, t in totals.items():
        summary.append(
            f"{repo:<24} {t['hit']/n:>9.0%} {t['strict']/n:>8.0%} {t['rr']/n:>6.2f} "
            f"{t['noise']:>6}/{n*k} ({t['noise']/(n*k):.0%})"
        )
    print("\n".join(summary))

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{date.today().isoformat()}_{golden_path.stem}_{'_vs_'.join(repos)}.txt"
    out.write_text("\n".join(summary) + "\n\n" + "\n\n".join(report) + "\n", encoding="utf-8")
    print(f"\nper-query results: {out.relative_to(_SERVICE_DIR)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("golden", type=Path, help="golden set JSON file")
    parser.add_argument("repos", nargs="+", help="repository_id(s) to evaluate")
    args = parser.parse_args()
    asyncio.run(run(args.golden, args.repos))


if __name__ == "__main__":
    main()
