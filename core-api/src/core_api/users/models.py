from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    # GitHub's numeric user ID — stable, unique, never changes.
    # BigInteger because GitHub IDs are 64-bit.
    github_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)

    # GitHub login (username). Can change on GitHub's side — don't use as identity.
    github_login: Mapped[str] = mapped_column(String(255), nullable=False)

    # Encrypted GitHub OAuth access token. Ciphertext, base64-ish.
    encrypted_access_token: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )