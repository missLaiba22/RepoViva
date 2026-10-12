"""Tests for GET /internal/v1/repositories/{id}/areas (decision 052).

Same approach as test_chunks_endpoint.py: call the handler directly,
bypassing HMAC, with a fake pool returning per-file chunk counts.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from repository_service.internal import router
from repository_service.internal.router import get_areas
from repository_service.main import app


class FakePool:
    def __init__(self, file_counts: dict[str, int]):
        self._rows = [{"filename": f, "chunk_count": n} for f, n in file_counts.items()]
        self.args = None

    async def fetch(self, query, *args):
        self.args = args
        return self._rows


async def _areas(monkeypatch, file_counts: dict[str, int], limit: int = 6) -> list[dict]:
    pool = FakePool(file_counts)
    monkeypatch.setattr(router, "get_db_pool", lambda: pool)
    response = await get_areas(repository_id=42, limit=limit)
    # repository_id is TEXT in code_chunks, as for /retrieve.
    assert pool.args == ("42",)
    return response.model_dump()["areas"]


async def test_top_level_directories_largest_first_with_limit(monkeypatch) -> None:
    areas = await _areas(
        monkeypatch,
        {
            "core-api/main.py": 3,
            "core-api/auth/router.py": 5,
            "frontend/src/App.tsx": 9,
            "docs/architecture.md": 1,
            "README.md": 2,
        },
        limit=2,
    )

    assert areas == [
        {"path": "frontend/", "chunk_count": 9},
        {"path": "core-api/", "chunk_count": 8},
    ]


async def test_single_directory_steps_down_until_two(monkeypatch) -> None:
    areas = await _areas(
        monkeypatch,
        {
            "src/app/orders/service.py": 4,
            "src/app/payments/webhook.py": 6,
            "setup.py": 1,
        },
    )

    assert areas == [
        {"path": "src/app/payments/", "chunk_count": 6},
        {"path": "src/app/orders/", "chunk_count": 4},
    ]


async def test_files_are_areas_when_there_are_no_directories(monkeypatch) -> None:
    areas = await _areas(monkeypatch, {"main.py": 3, "utils.py": 3, "db.py": 5})

    assert areas == [
        {"path": "db.py", "chunk_count": 5},
        {"path": "main.py", "chunk_count": 3},
        {"path": "utils.py", "chunk_count": 3},
    ]


async def test_no_chunks_gives_no_areas(monkeypatch) -> None:
    assert await _areas(monkeypatch, {}) == []


@pytest.mark.parametrize("limit", [0, 51])
def test_limit_is_bounded(limit) -> None:
    app.dependency_overrides[router.verify_hmac] = lambda: None
    try:
        response = TestClient(app).get(f"/internal/v1/repositories/42/areas?limit={limit}")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422
