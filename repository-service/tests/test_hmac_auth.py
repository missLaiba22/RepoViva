"""Tests for HMAC signing/verification.

Auth code is high-stakes: 'sort of correct' is worse than 'clearly wrong'.
These tests exist to prove each individual guarantee independently.
"""

import time

import pytest

from repository_service.internal.hmac_auth import (
    HmacVerificationError,
    MAX_AGE_SECONDS,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    sign,
    verify,
)

SECRET = "test-secret-not-a-real-one"
OTHER_SECRET = "different-secret"


def test_sign_and_verify_round_trip():
    """The basic happy path — what we sign, we can verify."""
    body = b'{"event_type": "ingestion.started"}'
    headers = sign(body=body, secret=SECRET)

    verify(
        body=body,
        timestamp_header=headers.timestamp,
        signature_header=headers.signature,
        secret=SECRET,
    )


def test_verify_rejects_wrong_secret():
    """A different secret must not produce a valid signature."""
    body = b'{"x": 1}'
    headers = sign(body=body, secret=SECRET)

    with pytest.raises(HmacVerificationError, match="signature mismatch"):
        verify(
            body=body,
            timestamp_header=headers.timestamp,
            signature_header=headers.signature,
            secret=OTHER_SECRET,
        )


def test_verify_rejects_tampered_body():
    """Changing the body after signing must break the signature."""
    original = b'{"amount": 10}'
    tampered = b'{"amount": 999}'
    headers = sign(body=original, secret=SECRET)

    with pytest.raises(HmacVerificationError, match="signature mismatch"):
        verify(
            body=tampered,
            timestamp_header=headers.timestamp,
            signature_header=headers.signature,
            secret=SECRET,
        )


def test_verify_rejects_stale_timestamp():
    """Requests older than the freshness window are rejected (replay protection)."""
    body = b"{}"
    old_ts = int(time.time()) - (MAX_AGE_SECONDS + 5)
    headers = sign(body=body, secret=SECRET, timestamp=old_ts)

    with pytest.raises(HmacVerificationError, match="freshness window"):
        verify(
            body=body,
            timestamp_header=headers.timestamp,
            signature_header=headers.signature,
            secret=SECRET,
        )


def test_verify_rejects_future_timestamp():
    """Timestamps too far in the future are also rejected —
    the window is bidirectional (guards against clock skew AND crafted timestamps).
    """
    body = b"{}"
    future_ts = int(time.time()) + (MAX_AGE_SECONDS + 5)
    headers = sign(body=body, secret=SECRET, timestamp=future_ts)

    with pytest.raises(HmacVerificationError, match="freshness window"):
        verify(
            body=body,
            timestamp_header=headers.timestamp,
            signature_header=headers.signature,
            secret=SECRET,
        )


def test_verify_rejects_missing_headers():
    """Missing either header is a rejection, not a crash."""
    with pytest.raises(HmacVerificationError, match="missing"):
        verify(body=b"{}", timestamp_header=None, signature_header="sha256=abc", secret=SECRET)

    with pytest.raises(HmacVerificationError, match="missing"):
        verify(body=b"{}", timestamp_header="123", signature_header=None, secret=SECRET)


def test_verify_rejects_malformed_timestamp():
    """A non-numeric timestamp is rejected cleanly, not with a ValueError."""
    with pytest.raises(HmacVerificationError, match="invalid timestamp"):
        verify(
            body=b"{}",
            timestamp_header="not-a-number",
            signature_header="sha256=abc",
            secret=SECRET,
        )


def test_verify_rejects_wrong_algorithm_prefix():
    """Signatures without the sha256= prefix are rejected —
    even if the raw digest would coincidentally match.
    """
    body = b"{}"
    headers = sign(body=body, secret=SECRET)
    raw_digest = headers.signature[len("sha256="):]

    with pytest.raises(HmacVerificationError, match="unsupported"):
        verify(
            body=body,
            timestamp_header=headers.timestamp,
            signature_header=raw_digest,  # no prefix
            secret=SECRET,
        )


def test_signed_headers_as_dict_uses_correct_names():
    """SignedHeaders.as_dict() produces the exact wire header names.
    Any drift here breaks interop with the other service.
    """
    headers = sign(body=b"{}", secret=SECRET).as_dict()
    assert TIMESTAMP_HEADER in headers
    assert SIGNATURE_HEADER in headers
    assert headers[SIGNATURE_HEADER].startswith("sha256=")