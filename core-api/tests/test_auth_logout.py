"""POST /v1/auth/github/logout and where the login callback sends the browser."""

from fastapi.testclient import TestClient

from core_api.auth import router as auth_router
from core_api.config import get_settings
from core_api.main import app


def test_logout_clears_session_cookie():
    client = TestClient(app)
    client.cookies.set(auth_router.SESSION_COOKIE, "signed-value")

    response = client.post("/v1/auth/github/logout")

    assert response.status_code == 204
    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith(f"{auth_router.SESSION_COOKIE}=")
    assert "Max-Age=0" in set_cookie
    assert "HttpOnly" in set_cookie


def test_logout_when_not_logged_in_is_fine():
    assert TestClient(app).post("/v1/auth/github/logout").status_code == 204


def test_logout_is_not_a_get():
    assert TestClient(app).get("/v1/auth/github/logout").status_code == 405


def test_callback_redirects_to_frontend_home(monkeypatch):
    monkeypatch.setattr(auth_router, "read_state", lambda signed: "s")
    monkeypatch.setattr(auth_router, "exchange_code_for_token", lambda code: "gho_x")
    monkeypatch.setattr(auth_router, "fetch_github_user", lambda token: {"id": 1, "login": "l"})
    monkeypatch.setattr(
        auth_router, "find_or_create_user", lambda db, **kw: type("U", (), {"id": 1})()
    )
    app.dependency_overrides[auth_router.get_db] = lambda: None
    try:
        client = TestClient(app, follow_redirects=False)
        client.cookies.set(auth_router.STATE_COOKIE, "signed-state")
        response = client.get("/v1/auth/github/callback", params={"code": "c", "state": "s"})
    finally:
        app.dependency_overrides.clear()

    expected = f"{get_settings().frontend_base_url.rstrip('/')}/home"
    assert response.status_code == 302
    assert response.headers["location"] == expected
    assert auth_router.SESSION_COOKIE in response.headers["set-cookie"]
