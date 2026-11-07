"""GET /v1/repositories/{id}/areas (decision 065), with the DB session,
current user and Repository Service faked."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from core_api.auth.dependencies import get_current_user
from core_api.db import get_db
from core_api.main import app
from core_api.repositories import areas_client
from core_api.repositories import router as repositories_router


@pytest.fixture
def client(monkeypatch):
    def lookup(db, *, repository_id, owner_user_id):
        return SimpleNamespace(id=15) if repository_id == 15 and owner_user_id == 1 else None

    monkeypatch.setattr(repositories_router.service, "get_repository_for_user", lookup)
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    yield TestClient(app)
    app.dependency_overrides.clear()


def fake_repository_service(monkeypatch, handler):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    real = areas_client.get_areas
    monkeypatch.setattr(areas_client, "get_areas", lambda repository_id: real(repository_id, http=http))


def test_areas_are_read_with_the_plan_limit_and_returned(client, monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = request.url
        return httpx.Response(200, json={"areas": [{"path": "src/api/", "chunk_count": 40}]})

    fake_repository_service(monkeypatch, handler)

    response = client.get("/v1/repositories/15/areas")

    assert response.status_code == 200
    assert response.json() == {"areas": [{"path": "src/api/", "chunk_count": 40}]}
    assert seen["url"].path == "/internal/v1/repositories/15/areas"
    assert seen["url"].params["limit"] == "6"


def test_repository_service_down_is_503(client, monkeypatch):
    fake_repository_service(monkeypatch, lambda request: httpx.Response(500, text="boom"))

    assert client.get("/v1/repositories/15/areas").status_code == 503


def test_someone_elses_repository_is_not_found(client):
    assert client.get("/v1/repositories/99/areas").status_code == 404
