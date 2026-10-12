from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from repoviva_common.dependencies import hmac_dependency
from repoviva_common.hmac_auth import sign

SECRET = "s3cret"

app = FastAPI()


@app.post("/internal/echo", dependencies=[Depends(hmac_dependency(lambda: SECRET))])
async def echo(payload: dict) -> dict:
    return payload


client = TestClient(app)


def test_signed_request_reaches_handler_with_parsed_body():
    body = b'{"x": 1}'
    headers = {"Content-Type": "application/json", **sign(body=body, secret=SECRET)}
    response = client.post("/internal/echo", content=body, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"x": 1}


def test_unsigned_request_is_401():
    response = client.post("/internal/echo", json={"x": 1})
    assert response.status_code == 401
    assert response.json() == {"detail": "unauthorized"}


def test_wrong_secret_is_401():
    body = b"{}"
    headers = {"Content-Type": "application/json", **sign(body=body, secret="other")}
    assert client.post("/internal/echo", content=body, headers=headers).status_code == 401
