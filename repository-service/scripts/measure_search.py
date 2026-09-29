"""Measure exact-search latency per repository (decision 033).

Usage: uv run python scripts/measure_search.py [repository_id ...]
(no args = every repository in code_chunks)

For each repository: chunk count, first-query (cold-ish) time, EXPLAIN
execution time, and warm median/p95 over 20 runs. Uses a stored chunk's
embedding as the query vector — no Voyage calls.
"""

import asyncio
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import asyncpg  # noqa: E402

from repository_service.config import get_settings  # noqa: E402
from repository_service.retrieval.search import _SEARCH_SQL  # noqa: E402

RUNS = 20


async def measure(conn: asyncpg.Connection, repo: str) -> None:
    n = await conn.fetchval(
        "SELECT count(*) FROM code_chunks WHERE repository_id = $1", repo
    )
    query_vec = await conn.fetchval(
        "SELECT embedding::text FROM code_chunks WHERE repository_id = $1 "
        "ORDER BY id LIMIT 1",
        repo,
    )
    args = (query_vec, repo, None, [], 10)

    t0 = time.perf_counter()
    await conn.fetch(_SEARCH_SQL, *args)
    first = (time.perf_counter() - t0) * 1000

    plan = await conn.fetch("EXPLAIN (ANALYZE) " + _SEARCH_SQL, *args)
    exec_ms = next(
        float(r[0].split(":")[1].split()[0])
        for r in plan if r[0].startswith("Execution Time")
    )
    # Innermost scan node, e.g. "Seq Scan on code_chunks" or
    # "Bitmap Index Scan on code_chunks_pkey".
    scan = [
        r[0].strip().removeprefix("->").strip().split("  (")[0]
        for r in plan if "Scan" in r[0]
    ][-1]

    timings = []
    for _ in range(RUNS):
        t0 = time.perf_counter()
        await conn.fetch(_SEARCH_SQL, *args)
        timings.append((time.perf_counter() - t0) * 1000)
    timings.sort()
    median, p95 = timings[RUNS // 2], timings[int(RUNS * 0.95) - 1]

    print(
        f"{repo:<10} {n:>7} {first:>9.1f} {exec_ms:>9.1f} {median:>9.1f} "
        f"{p95:>9.1f} {median * 1000 / n:>8.1f}   {scan}"
    )


async def main(repos: list[str]) -> None:
    conn = await asyncpg.connect(get_settings().database_url)
    try:
        if not repos:
            repos = [
                r[0] for r in await conn.fetch(
                    "SELECT repository_id FROM code_chunks GROUP BY 1 "
                    "ORDER BY count(*)"
                )
            ]
        print("indexes:", [
            r[0] for r in await conn.fetch(
                "SELECT indexname FROM pg_indexes WHERE tablename = 'code_chunks'"
            )
        ])
        print(
            f"\n{'repo':<10} {'chunks':>7} {'first ms':>9} {'exec ms':>9} "
            f"{'median ms':>9} {'p95 ms':>9} {'us/chunk':>8}   plan"
        )
        for repo in repos:
            await measure(conn, repo)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
