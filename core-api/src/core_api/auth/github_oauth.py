from urllib.parse import urlencode

import httpx

from core_api.config import get_settings

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"

# What we ask permission for. `read:user` gives us the profile.
# `repo` (added later) will give us repo read access when RAG needs it.
SCOPES = "read:user"


def build_authorize_url(state: str) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.github_oauth_redirect_uri,
        "scope": SCOPES,
        "state": state,
    }
    return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str) -> str:
    """POST the code to GitHub, get back an access token."""
    settings = get_settings()
    response = httpx.post(
        GITHUB_TOKEN_URL,
        data={
            "client_id": settings.github_client_id,
            "client_secret": settings.github_client_secret,
            "code": code,
            "redirect_uri": settings.github_oauth_redirect_uri,
        },
        headers={"Accept": "application/json"},
        timeout=10.0,
    )
    response.raise_for_status()
    payload = response.json()

    if "access_token" not in payload:
        raise RuntimeError(f"GitHub token exchange failed: {payload}")

    return payload["access_token"]


def fetch_github_user(access_token: str) -> dict:
    """Get the user's GitHub profile."""
    response = httpx.get(
        GITHUB_USER_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()