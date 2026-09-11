"""HMAC-SHA256 signing and verification for internal service-to-service calls.

Mirror of repository-service/src/repository_service/internal/hmac_auth.py.
Deliberately duplicated — the wire format is the contract, not the code
(see decision 027 and the write-twice choice in Step 2).

Wire format:
    signature = HMAC_SHA256(secret, f"{timestamp}.{body}")
    headers:
        X-Repoviva-Timestamp: <unix seconds>
        X-Repoviva-Signature: sha256=<hex digest>
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass

MAX_AGE_SECONDS = 60

TIMESTAMP_HEADER = "X-Repoviva-Timestamp"
SIGNATURE_HEADER = "X-Repoviva-Signature"
SIGNATURE_PREFIX = "sha256="


@dataclass(frozen=True)
class SignedHeaders:
    timestamp: str
    signature: str

    def as_dict(self) -> dict[str, str]:
        return {
            TIMESTAMP_HEADER: self.timestamp,
            SIGNATURE_HEADER: self.signature,
        }


class HmacVerificationError(Exception):
    """Raised when a request fails HMAC verification."""


def sign(*, body: bytes, secret: str, timestamp: int | None = None) -> SignedHeaders:
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
    received_digest = signature_header[len(SIGNATURE_PREFIX):]

    payload = f"{ts}.".encode() + body
    expected_digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(received_digest, expected_digest):
        raise HmacVerificationError("signature mismatch")