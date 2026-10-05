from fastapi.testclient import TestClient

from voice_service.main import app


def test_health_returns_ok():
    # Not used as a context manager, so the lifespan (DB pool) doesn't run.
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
