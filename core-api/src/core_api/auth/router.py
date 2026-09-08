import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from core_api.auth.github_oauth import (
    build_authorize_url,
    exchange_code_for_token,
    fetch_github_user,
)
from core_api.db import get_db
from core_api.security.cookies import (
    SESSION_MAX_AGE_SECONDS,
    STATE_MAX_AGE_SECONDS,
    read_state,
    sign_session,
    sign_state,
)
from core_api.users.service import find_or_create_user

router = APIRouter(prefix="/v1/auth/github", tags=["auth"])

STATE_COOKIE = "repoviva_oauth_state"
SESSION_COOKIE = "repoviva_session"

FRONTEND_AFTER_LOGIN_URL = "http://localhost:8000/docs"
# ^ For now, after login we send you to the Swagger UI so you can hit /v1/me.
# Will point to the real frontend URL once the frontend exists.


@router.get("/login")
def login() -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    signed = sign_state(state)
    authorize_url = build_authorize_url(state)

    response = RedirectResponse(url=authorize_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=STATE_COOKIE,
        value=signed,
        max_age=STATE_MAX_AGE_SECONDS,
        httponly=True,
        secure=False,          # localhost is http; flip to True in production
        samesite="lax",
        path="/",
    )
    return response


@router.get("/callback")
def callback(
    request: Request,
    code: str,
    state: str,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    # 1. Verify state
    signed_state = request.cookies.get(STATE_COOKIE)
    if signed_state is None:
        raise HTTPException(status_code=400, detail="Missing state cookie")

    expected_state = read_state(signed_state)
    if expected_state is None or expected_state != state:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    # 2. Exchange code for token
    access_token = exchange_code_for_token(code)

    # 3. Fetch user profile
    profile = fetch_github_user(access_token)
    github_user_id = profile["id"]
    github_login = profile["login"]

    # 4. Find or create the user
    user = find_or_create_user(
        db,
        github_user_id=github_user_id,
        github_login=github_login,
        access_token=access_token,
    )

    # 5. Set session, clear state cookie, redirect
    response = RedirectResponse(url=FRONTEND_AFTER_LOGIN_URL, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=sign_session(user.id),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )
    response.delete_cookie(key=STATE_COOKIE, path="/")
    return response