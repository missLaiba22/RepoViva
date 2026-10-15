"""Request IDs across services (decision 056).

The ID lives in a context variable, which asyncio tasks, `asyncio.to_thread`
and Starlette's threadpool all copy, so work started from a request keeps it.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER = "X-Request-ID"
_VALID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s"

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


def new_request_id() -> str:
    return uuid4().hex


@contextmanager
def request_id_scope(request_id: str | None = None) -> Iterator[str]:
    """Run a block under `request_id`, or a new one if it is missing or invalid."""
    if request_id is None or not _VALID.match(request_id):
        request_id = new_request_id()
    token = _request_id.set(request_id)
    try:
        yield request_id
    finally:
        _request_id.reset(token)


class RequestIDMiddleware:
    """Gives each HTTP request and WebSocket connection an ID and echoes it back."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        incoming = _header(scope, HEADER.lower().encode())
        with request_id_scope(incoming) as request_id:
            reply_header = (HEADER.lower().encode(), request_id.encode())

            async def send_with_id(message: Message) -> None:
                if message["type"] in ("http.response.start", "websocket.accept"):
                    message = {**message, "headers": [*message.get("headers", []), reply_header]}
                await send(message)

            await self.app(scope, receive, send_with_id)


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1")
    return None


class _RequestIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


def configure_logging(level: int = logging.INFO) -> None:
    """One log format for every service, with the request ID in each line."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    handler.addFilter(_RequestIDFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
