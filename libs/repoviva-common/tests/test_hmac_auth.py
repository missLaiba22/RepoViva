import hashlib
import hmac

import pytest

from repoviva_common.hmac_auth import (
    MAX_AGE_SECONDS,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    HmacVerificationError,
    sign,
    verify,
)

SECRET = "s3cret"
NOW = 1_700_000_000


def _signed(body: bytes, *, timestamp: int = NOW) -> dict[str, str]:
    return sign(body=body, secret=SECRET, timestamp=timestamp)


def _verify(body: bytes, headers: dict[str, str], *, secret: str = SECRET, now: int = NOW) -> None:
    verify(
        body=body,
        timestamp_header=headers[TIMESTAMP_HEADER],
        signature_header=headers[SIGNATURE_HEADER],
        secret=secret,
        now=now,
    )


def test_sign_matches_wire_format():
    body = b'{"token":"abc"}'
    headers = _signed(body)

    expected = hmac.new(SECRET.encode(), b"1700000000." + body, hashlib.sha256).hexdigest()
    assert headers == {TIMESTAMP_HEADER: "1700000000", SIGNATURE_HEADER: f"sha256={expected}"}


def test_verify_accepts_own_signature():
    _verify(b"{}", _signed(b"{}"), now=NOW + 30)


@pytest.mark.parametrize(
    ("timestamp_header", "signature_header", "reason"),
    [
        (None, "sha256=x", "missing"),
        (str(NOW), None, "missing"),
        ("soon", "sha256=x", "invalid timestamp"),
        (str(NOW), "md5=x", "unsupported"),
        (str(NOW), "sha256=" + "0" * 64, "signature mismatch"),
    ],
)
def test_verify_rejects_malformed(timestamp_header, signature_header, reason):
    with pytest.raises(HmacVerificationError, match=reason):
        verify(
            body=b"",
            timestamp_header=timestamp_header,
            signature_header=signature_header,
            secret=SECRET,
            now=NOW,
        )


def test_verify_rejects_tampered_body():
    with pytest.raises(HmacVerificationError, match="signature mismatch"):
        _verify(b'{"amount": 999}', _signed(b'{"amount": 10}'))


def test_verify_rejects_wrong_secret():
    with pytest.raises(HmacVerificationError, match="signature mismatch"):
        _verify(b"{}", _signed(b"{}"), secret="other")


@pytest.mark.parametrize("skew", [MAX_AGE_SECONDS + 1, -(MAX_AGE_SECONDS + 1)])
def test_verify_rejects_timestamp_outside_window(skew):
    with pytest.raises(HmacVerificationError, match="freshness window"):
        _verify(b"", _signed(b""), now=NOW + skew)
