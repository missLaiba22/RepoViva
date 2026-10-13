"""Regression: re-ingestion failed on Windows because git's pack files are read-only."""

from __future__ import annotations

import stat
from pathlib import Path

from repository_service.ingestion.workspace import prepare_clean_workspace


def test_prepare_clean_workspace_removes_read_only_files(tmp_path: Path) -> None:
    pack = tmp_path / "18" / ".git" / "objects" / "pack" / "pack-1.idx"
    pack.parent.mkdir(parents=True)
    pack.write_bytes(b"x")
    pack.chmod(stat.S_IREAD)

    path = prepare_clean_workspace("18", tmp_path)

    assert path == (tmp_path / "18").resolve()
    assert not path.exists()
