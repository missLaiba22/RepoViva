# repository-service/tests/test_path_matcher.py
"""Which repository files the indexing flow picks up (indexing/flow.py)."""

from pathlib import PurePosixPath

import pytest

from repository_service.indexing.flow import PATH_MATCHER


@pytest.mark.parametrize(
    "path",
    [
        "fastapi/routing.py",
        "README.md",
        "docs/en/docs/tutorial/query-params.md",
        "docs/api/reference.md",
        "docs/guide/intro.md",
        "docs/index.md",
        "src/app/index.ts",
    ],
)
def test_included(path: str) -> None:
    assert PATH_MATCHER.is_file_included(PurePosixPath(path))


@pytest.mark.parametrize(
    "path",
    [
        "docs/hi/docs/tutorial/query-params.md",
        "docs/zh-hant/docs/index.md",
        "docs/pt/docs/async.md",
        "website/docs/fr/intro.md",
        "i18n/ja/docusaurus-plugin-content-docs/current/intro.md",
        "node_modules/pkg/index.js",
        "poetry.lock",
    ],
)
def test_excluded(path: str) -> None:
    assert not PATH_MATCHER.is_file_included(PurePosixPath(path))
