# repository-service/src/repository_service/ingestion/workspace.py
"""Workspace layout for cloned repositories.

Each ingested repository gets its own directory under WORKSPACE_ROOT,
keyed by repository_id. The clone is scratch space used during
ingestion; the durable result is the repository snapshot data, chunks,
and embeddings stored in Postgres.

The workspace is treated as ephemeral. A service restart or
redeployment may remove the clone, so re-ingestion must be able to
clone the repository again. Any optimization to reuse an existing
clone can be added later without making persistence a requirement.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def workspace_for(repository_id: str, workspace_root: Path) -> Path:
    """Return the workspace path for a repository. Does not touch disk.

    Resolved to an absolute path — a relative `workspace_root` (e.g. from
    `WORKSPACE_ROOT=workspace` in .env) would otherwise reach CocoIndex's
    `index_file` as a relative `sourcedir`, which can't be compared against
    the absolute paths CocoIndex resolves internally (`Path.relative_to`
    requires both sides to agree on absolute vs. relative).
    """
    return (workspace_root / repository_id).resolve()


def prepare_clean_workspace(repository_id: str, workspace_root: Path) -> Path:
    """Ensure the workspace path is clear before a fresh clone.

    Returns the path. Does NOT create the directory itself — `git clone`
    creates it. If a previous clone exists there, it's removed. The
    parent (WORKSPACE_ROOT) is created if missing.

    Callers must not depend on the workspace persisting after the
    ingestion job completes — see the module docstring.
    """
    path = workspace_for(repository_id, workspace_root)
    if path.exists():
        shutil.rmtree(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path