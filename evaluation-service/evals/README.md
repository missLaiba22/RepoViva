# Grading evals

A hand-written sanity set and a harness that checks whether grading ranks
known-good answers above known-bad ones. Nothing else measures grading
quality: unit tests use a fake model, and a real report can only be read
by eye (`scripts/eval_report.py`).

## Run

From `evaluation-service/`, with Repository Service running and
`GROQ_API_KEY` set:

```
uv run python evals/grader_sanity.py evals/golden/grader_sanity_v1.json --runs 3
```

Add `--repo http://localhost:8001` if Repository Service isn't at the
`.env` URL. The set's chunks must exist in that database (repository 15).

Each run of set v1 grades 6 answers (about 16k tokens). Groq's free tier allows
200,000 tokens a day for the grading model (decision 051), so three runs
use about a quarter of a day's budget.

## Checks

Per case and run, on the correctness score (decision 050):

| Check | Passes when |
|---|---|
| order | strong > vague and strong > wrong |
| strong | strong >= 4 |
| wrong | wrong <= 2 |
| names | the wrong answer's gaps or justification mention its actual mistake |

Every grade is written to `evals/results/`, named by date, set and
prompt version, for reading by eye.

## Rules for golden sets

- Answers and `wrong_mistake_keywords` are written from the code
  **before** any grading run, and never edited after. A better set is a
  new version (`grader_sanity_v2.json`), so earlier numbers stay
  comparable.
- Each case uses a real interview question and the exact chunk ids it
  was generated from (`turns.retrieved_chunk_ids`).

## Results so far

| File | Prompt | Result |
|---|---|---|
| `2026-10-07_grader_sanity_v1_v2.json` | v2 | 15/16 (2 runs) |
| `2026-10-08_grader_sanity_v1_v3.json` | v3 | 24/24 (3 runs) |
| `2026-10-08_grader_sanity_v1_v4-reverted.json` | v4, reverted | 24/24, no change from v3 |
| `2026-10-08_grader_sanity_v1_v5.json` | v5 | 24/24 (3 runs), same scores as v3 |
| `2026-10-09_grader_sanity_v2_v5.json` | v5 | 14/16 (1 run), 3/33 key points say "should" |
| `2026-10-09_grader_sanity_v2_v6-reverted.json` | v6, reverted | 26/32 (2 runs), same two failures, 2/68 "should" |

v5 is the prompt in use. Set v2's two failures are known limitations
(decision 050):

- `abandoned-checkout-stock`: the wrong answer gets 3, not <= 2, though
  its own gap calls the claim untrue.
- `chat-db-drop-unseen-code`: the strong answer gets 2, because the
  code it describes isn't in the question's excerpts.

Each run of set v2 grades 12 answers (about 32k tokens).
