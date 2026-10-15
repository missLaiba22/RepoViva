import json
import logging

import httpx
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from repoviva_common import messaging
from repoviva_common.http import create_async_client, create_sync_client
from repoviva_common.messaging import Message, build_message, handle_one, send_job
from repoviva_common.request_id import (
    HEADER,
    RequestIDMiddleware,
    configure_logging,
    get_request_id,
    request_id_scope,
)


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/")
    def seen() -> dict[str, str | None]:
        return {"request_id": get_request_id()}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_json({"request_id": get_request_id()})
        await websocket.close()

    return app


def test_valid_incoming_id_is_used_and_echoed():
    response = TestClient(_app()).get("/", headers={HEADER: "abc-123"})
    assert response.headers[HEADER] == "abc-123"
    assert response.json() == {"request_id": "abc-123"}


def test_invalid_or_missing_id_is_replaced():
    client = TestClient(_app())
    for headers in ({HEADER: "bad id!"}, {HEADER: "a" * 65}, {}):
        response = client.get("/", headers=headers)
        assert response.headers[HEADER] == response.json()["request_id"]
        assert response.headers[HEADER] != headers.get(HEADER)


def test_websocket_gets_an_id():
    with TestClient(_app()).websocket_connect("/ws", headers={HEADER: "ws-1"}) as ws:
        assert ws.receive_json() == {"request_id": "ws-1"}


def _echo(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"request_id": request.headers.get(HEADER)})


async def test_clients_forward_the_current_id():
    async with create_async_client(transport=httpx.MockTransport(_echo)) as client:
        assert (await client.get("http://x/")).json() == {"request_id": None}
        with request_id_scope("out-1"):
            assert (await client.get("http://x/")).json() == {"request_id": "out-1"}

    with create_sync_client(transport=httpx.MockTransport(_echo)) as client, \
            request_id_scope("out-2"):
        assert client.get("http://x/").json() == {"request_id": "out-2"}


class _FakeSqs:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send_message(self, **kwargs) -> None:
        self.sent.append(kwargs)

    def delete_message(self, **kwargs) -> None:
        pass

    def change_message_visibility(self, **kwargs) -> None:
        pass


def test_sent_message_carries_the_current_id(monkeypatch):
    sqs = _FakeSqs()
    monkeypatch.setattr(messaging, "_sqs", sqs)
    with request_id_scope("job-1"):
        send_job("q", "t", {})
    assert json.loads(sqs.sent[0]["MessageBody"])["request_id"] == "job-1"


async def test_handler_runs_under_the_message_id():
    seen: list[str | None] = []

    async def handler(message: Message) -> None:
        seen.append(get_request_id())

    with request_id_scope("msg-1"):
        message = build_message("t", {})
    await handle_one(_FakeSqs(), "q", {"ReceiptHandle": "r", "Body": message.model_dump_json()},
                     handler)
    legacy = build_message("t", {})
    await handle_one(_FakeSqs(), "q", {"ReceiptHandle": "r", "Body": legacy.model_dump_json()},
                     handler)

    assert seen[0] == "msg-1"
    assert seen[1] is not None
    assert get_request_id() is None


def test_log_lines_include_the_id(capsys):
    configure_logging()
    logger = logging.getLogger("test")
    logger.info("outside")
    with request_id_scope("log-1"):
        logger.info("inside")
    err = capsys.readouterr().err
    assert "[-]: outside" in err
    assert "[log-1]: inside" in err
