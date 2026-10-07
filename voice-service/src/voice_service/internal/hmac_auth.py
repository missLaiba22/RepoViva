"""HMAC-SHA256 signing and verification for Voice Service's internal calls.

Wire format (decision 027):
    signature = HMAC_SHA256(secret, f"{timestamp}.{body}")
    headers:
        X-Repoviva-Timestamp: <unix seconds>
        X-Repoviva-Signature: sha256=<hex digest>

Written again here on purpose rather than shared as a package ("write it
twice, deliberately" — the wire format is the contract). Signing covers
outbound calls to Core API and Repository Service; verification covers
the inbound turns endpoint Evaluation Service calls (decision 049).
"""

from __future__ import annotations

import hashlib
import hmac
import time

TIMESTAMP_HEADER = "X-Repoviva-Timestamp"
SIGNATURE_HEADER = "X-Repoviva-Signature"
SIGNATURE_PREFIX = "sha256="

# Freshness window (decision 027): older requests are rejected so a
# captured signature can't be replayed.
MAX_AGE_SECONDS = 60


class HmacVerificationError(Exception):
    """An inbound request failed verification. Every cause maps to 401."""


def _digest(secret: str, timestamp: str, body: bytes) -> str:
    payload = f"{timestamp}.".encode() + body
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def sign(*, body: bytes, secret: str, timestamp: int | None = None) -> dict[str, str]:
    """Return the two headers to attach to a request carrying exactly `body`.

    `body` must be the bytes that go on the wire — sign and send the same
    bytes, or the receiver's check fails.
    """
    ts = str(timestamp if timestamp is not None else int(time.time()))
    return {
        TIMESTAMP_HEADER: ts,
        SIGNATURE_HEADER: f"{SIGNATURE_PREFIX}{_digest(secret, ts, body)}",
    }


def verify(
    *,
    body: bytes,
    timestamp_header: str | None,
    signature_header: str | None,
    secret: str,
    now: int | None = None,
) -> None:
    """Raise HmacVerificationError unless the headers sign `body` and are fresh.

    `body` is the raw bytes as received (empty for a GET), never re-serialized
    JSON.
    """
    if timestamp_header is None or signature_header is None:
        raise HmacVerificationError("missing signature headers")
    try:
        ts = int(timestamp_header)
    except ValueError as exc:
        raise HmacVerificationError("invalid timestamp") from exc

    current = now if now is not None else int(time.time())
    if abs(current - ts) > MAX_AGE_SECONDS:
        raise HmacVerificationError("timestamp outside freshness window")

    if not signature_header.startswith(SIGNATURE_PREFIX):
        raise HmacVerificationError("unsupported signature algorithm")
    received = signature_header[len(SIGNATURE_PREFIX):]

    # Constant-time comparison: == would leak the digest through timing.
    if not hmac.compare_digest(received, _digest(secret, timestamp_header, body)):
        raise HmacVerificationError("signature mismatch")
