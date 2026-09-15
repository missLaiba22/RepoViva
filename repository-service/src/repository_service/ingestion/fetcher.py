# repository-service/src/repository_service/ingestion/fetcher.py

"""Shallow git clone of a GitHub repo into a repository workspace."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from repository_service.ingestion.workspace import prepare_clean_workspace

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FetchResult:
    clone_path: Path
    commit_sha: str


class FetchError(Exception):
    """Raised when repository fetching fails."""


_CLONE_TIMEOUT_SECONDS = 120.0


def _run_git_clone(github_url: str, target: Path) -> None:
    """Run a blocking git clone and raise FetchError on failure."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", github_url, str(target)],
            capture_output=True,
            env=env,
            timeout=_CLONE_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise FetchError("git is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise FetchError(
            f"git clone timed out after {_CLONE_TIMEOUT_SECONDS:.0f}s"
        ) from exc

    if result.returncode != 0:
        stderr_text = result.stderr.decode(
            "utf-8", errors="replace"
        )[:500].strip()
        raise FetchError(
            f"git clone failed (exit {result.returncode}): {stderr_text}"
        )


def _read_head_sha(clone_path: Path) -> str:
    """Read the HEAD commit SHA from a cloned repository."""
    try:
        result = subprocess.run(
            ["git", "-C", str(clone_path), "rev-parse", "HEAD"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except FileNotFoundError as exc:
        raise FetchError("git is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise FetchError("git rev-parse HEAD timed out") from exc

    if result.returncode != 0:
        stderr_text = result.stderr.decode(
            "utf-8", errors="replace"
        )[:200].strip()
        raise FetchError(
            f"failed to read HEAD sha (exit {result.returncode}): {stderr_text}"
        )

    return result.stdout.decode("utf-8").strip()


async def fetch_repository(
    *,
    repository_id: str,
    github_url: str,
    workspace_root: Path,
) -> FetchResult:
    """Shallow-clone a public GitHub repo and return its path and HEAD SHA."""
    target = prepare_clean_workspace(repository_id, workspace_root)

    logger.info(
        "cloning %s to %s (shallow, depth=1)",
        github_url,
        target,
    )

    await asyncio.to_thread(_run_git_clone, github_url, target)
    commit_sha = await asyncio.to_thread(_read_head_sha, target)

    logger.info(
        "clone complete: %s @ %s",
        target,
        commit_sha[:7],
    )

    return FetchResult(
        clone_path=target,
        commit_sha=commit_sha,
    )

