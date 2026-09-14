# repository-service/tests/test_fetcher.py
"""Tests for the git-clone fetcher.

The happy-path test hits GitHub over the network. This is a real
tradeoff: mocking `git clone` would just be testing our mocks and
would miss real-world failure modes (proxy quirks, DNS, cert issues).
We accept the flakiness and mark it with the `integration` marker so
fast local runs can skip it with `-m "not integration"`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from repository_service.ingestion.fetcher import FetchError, fetch_repository


@pytest.mark.integration
@pytest.mark.asyncio
async def test_clones_public_repo_shallow(tmp_path: Path) -> None:
    result = await fetch_repository(
        repository_id="test-hello",
        github_url="https://github.com/octocat/Hello-World.git",
        workspace_root=tmp_path,
    )

    assert result == tmp_path / "test-hello"
    assert result.is_dir()
    assert (result / ".git").is_dir()
    # Hello-World has a README (no extension) at the top level.
    assert (result / "README").is_file()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invalid_url_raises_fetch_error(tmp_path: Path) -> None:
    with pytest.raises(FetchError):
        await fetch_repository(
            repository_id="test-bad",
            github_url="https://github.com/definitely-not-a-real-user-9x8z7q/nope.git",
            workspace_root=tmp_path,
        )