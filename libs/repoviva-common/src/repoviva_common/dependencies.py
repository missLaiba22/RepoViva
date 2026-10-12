"""FastAPI dependencies for internal endpoints."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, status

from repoviva_common.hmac_auth import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    HmacVerificationError,
    verify,
)


def hmac_dependency(get_secret: Callable[[], str]) -> Callable[[Request], Awaitable[None]]:
    """A dependency that returns 401 unless the request is signed with `get_secret()`.

    The secret is read per request, so tests can override settings.
    """

    async def verify_hmac(request: Request) -> None:
        try:
            verify(
                body=await request.body(),
                timestamp_header=request.headers.get(TIMESTAMP_HEADER),
                signature_header=request.headers.get(SIGNATURE_HEADER),
                secret=get_secret(),
            )
        except HmacVerificationError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="unauthorized") from exc

    return verify_hmac
