from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.security.token_crypto import encrypt_token
from core_api.users.models import User


def find_or_create_user(
    db: Session,
    *,
    github_user_id: int,
    github_login: str,
    access_token: str,
) -> User:
    """Look up a user by their GitHub numeric ID. Create if not found.
    Always updates the stored access token and login (they may have changed).
    """
    stmt = select(User).where(User.github_user_id == github_user_id)
    user = db.scalars(stmt).one_or_none()

    encrypted = encrypt_token(access_token)

    if user is None:
        user = User(
            github_user_id=github_user_id,
            github_login=github_login,
            encrypted_access_token=encrypted,
        )
        db.add(user)
    else:
        user.github_login = github_login
        user.encrypted_access_token = encrypted

    db.commit()
    db.refresh(user)
    return user