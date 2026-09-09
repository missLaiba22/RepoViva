"""HMAC-SHA256 signing and verification for internal service-to-service calls.

Wire format (decision 027):
    signature = HMAC_SHA256(secret, f"{timestamp}.{body}")
    headers:
        X-Repoviva-Timestamp: <unix seconds>
        X-Repoviva-Signature: sha256=<hex digest>

Receivers reject requests older than MAX_AGE_SECONDS.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass

# Freshness window — decision 027. Requests older than this are rejected
# to prevent replay of captured signatures.
MAX_AGE_SECONDS = 60

TIMESTAMP_HEADER = "X-Repoviva-Timestamp"
SIGNATURE_HEADER = "X-Repoviva-Signature"
SIGNATURE_PREFIX = "sha256="


@dataclass(frozen=True)
class SignedHeaders:
    """The two headers a sender must attach to a signed request."""

    timestamp: str
    signature: str

    def as_dict(self) -> dict[str, str]:
        return {
            TIMESTAMP_HEADER: self.timestamp,
            SIGNATURE_HEADER: self.signature,
        }


class HmacVerificationError(Exception):
    """Raised when a request fails HMAC verification.

    A single exception type on purpose — the caller shouldn't need to
    distinguish 'bad signature' from 'stale timestamp'. Both mean
    'reject this request with 401'.
    """


def sign(*, body: bytes, secret: str, timestamp: int | None = None) -> SignedHeaders:
    """Compute HMAC headers for an outbound request.

    Args:
        body: The exact request body bytes that will be sent on the wire.
              Must be bytes, not a dict or string — signing has to happen
              over the same bytes the receiver will see.
        secret: The shared HMAC secret.
        timestamp: Unix seconds. Defaults to now; overridable for testing.

    Returns:
        SignedHeaders — attach both headers to the outbound request.
    """
    ts = str(timestamp if timestamp is not None else int(time.time()))
    payload = f"{ts}.".encode() + body
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return SignedHeaders(timestamp=ts, signature=f"{SIGNATURE_PREFIX}{digest}")


def verify(
    *,
    body: bytes,
    timestamp_header: str | None,
    signature_header: str | None,
    secret: str,
    now: int | None = None,
) -> None:
    """Verify an inbound request's HMAC.

    Raises HmacVerificationError on any failure. Returns None on success.

    Args:
        body: The exact request body bytes as received on the wire.
              The caller must pass raw bytes, not parsed JSON — subtle
              re-serialization differences would break the signature.
        timestamp_header: Value of the X-Repoviva-Timestamp header, if present.
        signature_header: Value of the X-Repoviva-Signature header, if present.
        secret: The shared HMAC secret.
        now: Current unix seconds. Defaults to now; overridable for testing.
    """
    if timestamp_header is None or signature_header is None:
        raise HmacVerificationError("missing signature headers")

    # Parse timestamp.
    try:
        ts = int(timestamp_header)
    except ValueError as exc:
        raise HmacVerificationError("invalid timestamp") from exc

    # Freshness check — reject stale requests (replay protection).
    current = now if now is not None else int(time.time())
    if abs(current - ts) > MAX_AGE_SECONDS:
        raise HmacVerificationError("timestamp outside freshness window")

    # Parse signature — must start with the algorithm tag.
    if not signature_header.startswith(SIGNATURE_PREFIX):
        raise HmacVerificationError("unsupported signature algorithm")
    received_digest = signature_header[len(SIGNATURE_PREFIX):]

    # Recompute expected signature over the exact same bytes the sender signed.
    payload = f"{ts}.".encode() + body
    expected_digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    # Constant-time comparison — never use == here (timing attack).
    if not hmac.compare_digest(received_digest, expected_digest):
        raise HmacVerificationError("signature mismatch")