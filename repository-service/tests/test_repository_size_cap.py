# repository-service/tests/test_repository_size_cap.py
"""The pre-embedding repository size cap (decision 033).

No Postgres or Voyage: build_app is replaced with a stub that fails the
test if reached, which is how "rejected before any embedding" is checked.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from repository_service.indexing import runner
from repository_service.indexing.flow import split_source
from repository_service.indexing.runner import (
    RepositoryTooLargeError,
    count_chunks,
    run_indexing,
)
from repository_service.ingestion import orchestrator


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    # write_bytes, not write_text: on Windows write_text turns \n into \r\n,
    # which splits differently from the in-memory string used for `expected`.
    path.write_bytes(text.encode("utf-8"))


_CODE = "\n".join(f"def f{i}(x):\n    return x + {i}\n" for i in range(200))


def test_count_chunks_matches_split_and_skips_excluded(tmp_path: Path) -> None:
    _write(tmp_path, "app/main.py", _CODE)
    _write(tmp_path, "docs/en/index.md", "# Hello\n\nEnglish docs.\n")
    # Excluded: translations, node_modules, non-indexed extension.
    _write(tmp_path, "docs/fr/index.md", _CODE)
    _write(tmp_path, "node_modules/pkg/index.js", _CODE)
    _write(tmp_path, "data.csv", _CODE)

    expected = len(split_source("app/main.py", _CODE)[1]) + len(
        split_source("docs/en/index.md", "# Hello\n\nEnglish docs.\n")[1]
    )
    assert expected > 1
    assert count_chunks(tmp_path) == expected


async def test_run_indexing_rejects_before_embedding(tmp_path, monkeypatch) -> None:
    _write(tmp_path, "app/main.py", _CODE)
    monkeypatch.setattr(runner, "MAX_REPO_CHUNKS", 1)

    def build_app_must_not_run(**_kwargs):
        raise AssertionError("build_app reached — embedding would have started")

    monkeypatch.setattr(runner, "build_app", build_app_must_not_run)

    with pytest.raises(RepositoryTooLargeError) as info:
        await run_indexing(
            repository_id="r1", commit_sha="a" * 40, source_dir=tmp_path, pool=None,
        )
    assert info.value.limit == 1
    assert info.value.chunk_count == count_chunks(tmp_path)


async def test_orchestrator_reports_too_large_as_failed(monkeypatch) -> None:
    events: list[tuple] = []

    class FakeClient:
        async def emit_event(self, repository_id, event, data=None):
            events.append((repository_id, event, data))

    class FakeFetchResult:
        clone_path = Path("/unused")
        commit_sha = "b" * 40

    async def fake_fetch(**_kwargs):
        return FakeFetchResult()

    async def fake_run_indexing(**_kwargs):
        raise RepositoryTooLargeError(7_169, 6_000)

    monkeypatch.setattr(orchestrator, "get_core_api_client", lambda: FakeClient())
    monkeypatch.setattr(orchestrator, "fetch_repository", fake_fetch)
    monkeypatch.setattr(orchestrator, "run_indexing", fake_run_indexing)
    monkeypatch.setattr(orchestrator, "get_db_pool", lambda: None)

    await orchestrator.run_ingestion(
        repository_id="14", github_url="https://github.com/x/y",
        workspace_root=Path("/unused"),
    )

    assert events[-1] == (
        "14", "ingestion.failed",
        {"error_message": "repository too large: 7,169 chunks (limit 6,000)"},
    )
