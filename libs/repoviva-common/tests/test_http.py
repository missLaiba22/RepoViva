import httpx
import pytest

from repoviva_common.http import (
    DEFAULT_TIMEOUT,
    close_async_client,
    close_sync_client,
    create_async_client,
    create_sync_client,
    get_async_client,
    get_sync_client,
    open_async_client,
    open_sync_client,
)


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"timeout": request.extensions["timeout"]["read"]})


async def test_async_client_uses_default_timeout_and_allows_override():
    async with create_async_client(transport=httpx.MockTransport(_ok)) as client:
        assert (await client.get("http://x/")).json() == {"timeout": DEFAULT_TIMEOUT.read}
        assert (await client.get("http://x/", timeout=5.0)).json() == {"timeout": 5.0}


def test_sync_client_uses_default_timeout():
    with create_sync_client(transport=httpx.MockTransport(_ok)) as client:
        assert client.get("http://x/").json() == {"timeout": DEFAULT_TIMEOUT.read}


async def test_async_client_lifecycle():
    with pytest.raises(RuntimeError):
        get_async_client()
    open_async_client()
    client = get_async_client()
    assert get_async_client() is client
    await close_async_client()
    assert client.is_closed
    with pytest.raises(RuntimeError):
        get_async_client()


def test_sync_client_lifecycle():
    open_sync_client()
    client = get_sync_client()
    close_sync_client()
    assert client.is_closed
    with pytest.raises(RuntimeError):
        get_sync_client()
