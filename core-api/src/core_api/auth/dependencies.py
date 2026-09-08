from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.auth.router import SESSION_COOKIE
from core_api.db import get_db
from core_api.security.cookies import read_session
from core_api.users.models import User


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    signed = request.cookies.get(SESSION_COOKIE)
    if signed is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")

    user_id = read_session(signed)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    user = db.scalars(select(User).where(User.id == user_id)).one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user