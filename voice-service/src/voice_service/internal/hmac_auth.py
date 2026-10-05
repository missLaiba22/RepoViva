"""HMAC-SHA256 signing for Voice Service's outbound internal calls.

Wire format (decision 027):
    signature = HMAC_SHA256(secret, f"{timestamp}.{body}")
    headers:
        X-Repoviva-Timestamp: <unix seconds>
        X-Repoviva-Signature: sha256=<hex digest>

Written again here on purpose rather than shared as a package ("write it
twice, deliberately" — the wire format is the contract). Sign-only:
Voice Service receives no internal calls yet, so there is nothing to
verify.
"""

from __future__ import annotations

import hashlib
import hmac
import time

TIMESTAMP_HEADER = "X-Repoviva-Timestamp"
SIGNATURE_HEADER = "X-Repoviva-Signature"
SIGNATURE_PREFIX = "sha256="


def sign(*, body: bytes, secret: str, timestamp: int | None = None) -> dict[str, str]:
    """Return the two headers to attach to a request carrying exactly `body`.

    `body` must be the bytes that go on the wire — sign and send the same
    bytes, or the receiver's check fails.
    """
    ts = str(timestamp if timestamp is not None else int(time.time()))
    payload = f"{ts}.".encode() + body
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return {
        TIMESTAMP_HEADER: ts,
        SIGNATURE_HEADER: f"{SIGNATURE_PREFIX}{digest}",
    }
