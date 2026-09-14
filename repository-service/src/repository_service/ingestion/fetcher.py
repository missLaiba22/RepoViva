# repository-service/src/repository_service/ingestion/fetcher.py
"""Shallow git clone of a GitHub repo into a repository's workspace.

Calls the `git` binary via subprocess.run inside asyncio.to_thread.
We use a thread rather than asyncio.create_subprocess_exec because
the latter is unsupported on Windows with some event-loop policies
(uvicorn's default on Windows triggers NotImplementedError). Wrapping
a synchronous subprocess in a thread is cross-platform, semantically
equivalent for a one-shot background task, and simpler.

Safety measures still apply: no shell interpolation (argv, not string),
no interactive prompting (env), wall-clock cap via subprocess.run's
timeout parameter.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from pathlib import Path

from repository_service.ingestion.workspace import prepare_clean_workspace

logger = logging.getLogger(__name__)


class FetchError(Exception):
    """Raised when the clone fails for any reason.

    Wraps missing-git-binary errors, timeouts, and non-zero exit codes.
    The orchestrator turns this into an `ingestion.failed` event.
    """


# Wall-clock cap for a single clone. Public repos of the size RepoViva
# targets should finish well under this; anything slower is probably
# stuck (dead host, huge repo, hostile server).
_CLONE_TIMEOUT_SECONDS = 120.0


def _run_git_clone(github_url: str, target: Path) -> None:
    """Blocking git clone. Raises FetchError on any failure.

    Runs in a worker thread via asyncio.to_thread — the caller awaits it
    from the async orchestrator. Keeping the blocking call factored out
    here makes the error paths explicit and unit-testable.
    """
    # GIT_TERMINAL_PROMPT=0 makes git fail fast instead of prompting for
    # credentials on stdin. Without this, git will hang forever on a
    # private-repo or invalid-URL case.
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", github_url, str(target)],
            capture_output=True,
            env=env,
            timeout=_CLONE_TIMEOUT_SECONDS,
            check=False,  # we handle non-zero exit ourselves for a clearer error
        )
    except FileNotFoundError as exc:
        raise FetchError("git is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise FetchError(
            f"git clone timed out after {_CLONE_TIMEOUT_SECONDS:.0f}s"
        ) from exc

    if result.returncode != 0:
        # git puts useful diagnostics on stderr. Truncate to keep logs sane
        # if git decides to be verbose.
        stderr_text = result.stderr.decode("utf-8", errors="replace")[:500].strip()
        raise FetchError(
            f"git clone failed (exit {result.returncode}): {stderr_text}"
        )


async def fetch_repository(
    *,
    repository_id: str,
    github_url: str,
    workspace_root: Path,
) -> Path:
    """Shallow-clone a public GitHub repo into workspace/<repository_id>/.

    Returns the path to the local clone. Raises FetchError on any failure.
    Only public repos for now — private repos would require auth plumbing.
    """
    target = prepare_clean_workspace(repository_id, workspace_root)
    logger.info("cloning %s to %s (shallow, depth=1)", github_url, target)

    # Run the blocking git subprocess in a thread so we don't block the
    # event loop AND don't hit the asyncio-subprocess-on-Windows issue.
    await asyncio.to_thread(_run_git_clone, github_url, target)

    logger.info("clone complete: %s", target)
    return target