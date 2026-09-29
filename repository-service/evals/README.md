# Retrieval evals

Hand-written golden question sets and a harness that scores retrieval
against them. They exist because nothing else in the codebase measures
whether retrieval returns *useful* results: on the full FastAPI index,
71% of top-5 slots were translated docs, and no test or log showed it
(decision 033).

## Run

From `repository-service/`, with Postgres up and `VOYAGE_API_KEY` set:

```
uv run python evals/recall_eval.py evals/golden/fastapi.json <repository_id> [<repository_id> ...]
```

Pass several repository ids to compare index variants with identical query
embeddings. Costs one Voyage call per query. Per-query top-k is written to
`evals/results/`.

The repository must already be indexed. `fastapi/fastapi` is over the
6,000-chunk cap (decision 033), so reproducing its numbers requires
temporarily raising `MAX_REPO_CHUNKS` in `indexing/runner.py`.

## Rules for golden sets

- Relevance lists are written **before** looking at any results, and never
  edited after. A wrong or incomplete answer key is fixed by adding a new
  version of the set, so earlier numbers stay comparable.
- Relevance = regexes over repo-relative filenames. `noise_pattern` marks
  results that count as noise (e.g. translated docs) for the `strict` and
  `noise` metrics.

## Reading the numbers

Sets are small (20 queries). Treat results as direction, not decimals: one
query is 5 percentage points. Voyage query embeddings also vary slightly
between calls, which reorders near-ties — on the full FastAPI index a
re-run moved `strict` from 75% to 70% and noise from 71 to 72 slots, with
recall@5 and MRR unchanged (both runs are in `results/`).

## Results so far

| Date | Set | Index | recall@5 | strict | MRR | noise slots |
|---|---|---|---:|---:|---:|---:|
| 2026-09-30 | fastapi | full (22,333 chunks) | 90% | 75% | 0.80 | 71/100 |
| 2026-09-30 | fastapi | translations excluded (7,169) | 95% | 95% | 0.87 | 0/100 |
| 2026-09-30 | fastapi | full, re-run | 90% | 70% | 0.80 | 72/100 |

Known gap in `fastapi.json`: "Where are the Query, Path, Body and Header
parameter functions defined?" does not list
`docs/en/docs/reference/parameters.md`, which is relevant. It misses in
every variant equally.
