import hashlib
import hmac

import pytest

from evaluation_service.internal.hmac_auth import (
    MAX_AGE_SECONDS,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    HmacVerificationError,
    sign,
    verify,
)


def test_sign_matches_wire_format():
    """Recompute the signature the way every receiver does (decision 027)."""
    body = b'{"token":"abc"}'
    headers = sign(body=body, secret="s3cret", timestamp=1_700_000_000)

    expected = hmac.new(b"s3cret", b"1700000000." + body, hashlib.sha256).hexdigest()
    assert headers[TIMESTAMP_HEADER] == "1700000000"
    assert headers[SIGNATURE_HEADER] == f"sha256={expected}"


SECRET = "s3cret"
NOW = 1_700_000_000


def _signed(body: bytes, *, timestamp: int = NOW) -> dict[str, str]:
    return sign(body=body, secret=SECRET, timestamp=timestamp)


def test_verify_accepts_own_signature():
    headers = _signed(b"")
    verify(
        body=b"",
        timestamp_header=headers[TIMESTAMP_HEADER],
        signature_header=headers[SIGNATURE_HEADER],
        secret=SECRET,
        now=NOW + 30,
    )


@pytest.mark.parametrize(
    ("timestamp_header", "signature_header", "body", "now"),
    [
        (None, "sha256=x", b"", NOW),  # missing timestamp
        (str(NOW), None, b"", NOW),  # missing signature
        ("soon", "sha256=x", b"", NOW),  # unparseable timestamp
        (str(NOW), "md5=x", b"", NOW),  # wrong algorithm tag
        (str(NOW), "sha256=" + "0" * 64, b"", NOW),  # wrong digest
    ],
)
def test_verify_rejects_malformed(timestamp_header, signature_header, body, now):
    with pytest.raises(HmacVerificationError):
        verify(
            body=body,
            timestamp_header=timestamp_header,
            signature_header=signature_header,
            secret=SECRET,
            now=now,
        )


def test_verify_rejects_tampered_body():
    headers = _signed(b"original")
    with pytest.raises(HmacVerificationError):
        verify(
            body=b"tampered",
            timestamp_header=headers[TIMESTAMP_HEADER],
            signature_header=headers[SIGNATURE_HEADER],
            secret=SECRET,
            now=NOW,
        )


def test_verify_rejects_stale_timestamp():
    headers = _signed(b"")
    with pytest.raises(HmacVerificationError):
        verify(
            body=b"",
            timestamp_header=headers[TIMESTAMP_HEADER],
            signature_header=headers[SIGNATURE_HEADER],
            secret=SECRET,
            now=NOW + MAX_AGE_SECONDS + 1,
        )
