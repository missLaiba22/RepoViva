"""One long-lived httpx client per service (decision 055).

Keeps connections (and TLS sessions) open between calls. Callers that need
a different timeout pass `timeout=` on the request. Every request carries the
current request ID (decision 056).
"""

from __future__ import annotations

import httpx

from repoviva_common.request_id import HEADER, get_request_id

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=3.0)
DEFAULT_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20)
# Retries only failed connection attempts: the request never reached the server.
CONNECT_RETRIES = 1


def _add_request_id(request: httpx.Request) -> None:
    request_id = get_request_id()
    if request_id is not None:
        request.headers[HEADER] = request_id


async def _add_request_id_async(request: httpx.Request) -> None:
    _add_request_id(request)


def create_async_client(
    *, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        limits=DEFAULT_LIMITS,
        transport=transport or httpx.AsyncHTTPTransport(retries=CONNECT_RETRIES),
        event_hooks={"request": [_add_request_id_async]},
    )


def create_sync_client(*, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        timeout=DEFAULT_TIMEOUT,
        limits=DEFAULT_LIMITS,
        transport=transport or httpx.HTTPTransport(retries=CONNECT_RETRIES),
        event_hooks={"request": [_add_request_id]},
    )


# The process's one client, opened in the service's lifespan.
_async_client: httpx.AsyncClient | None = None
_sync_client: httpx.Client | None = None


def open_async_client() -> None:
    global _async_client
    _async_client = create_async_client()


async def close_async_client() -> None:
    global _async_client
    if _async_client is not None:
        await _async_client.aclose()
        _async_client = None


def get_async_client() -> httpx.AsyncClient:
    if _async_client is None:
        raise RuntimeError("HTTP client not opened — check the FastAPI lifespan")
    return _async_client


def open_sync_client() -> None:
    global _sync_client
    _sync_client = create_sync_client()


def close_sync_client() -> None:
    global _sync_client
    if _sync_client is not None:
        _sync_client.close()
        _sync_client = None


def get_sync_client() -> httpx.Client:
    if _sync_client is None:
        raise RuntimeError("HTTP client not opened — check the FastAPI lifespan")
    return _sync_client
