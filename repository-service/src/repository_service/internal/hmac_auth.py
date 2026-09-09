# """Shared HMAC sign/verify logic for the internal API.

# Both sides of the internal channel use this module:

# * repository-service  -> *verifies* inbound requests from core-api
# * core_api_client     -> *signs*    outbound event callbacks to core-api

# Signature scheme
# ----------------
#     message   = f"{timestamp}".encode() + b"." + raw_body
#     signature = hex( HMAC_SHA256(secret, message) )

# Two headers travel with every request:

#     X-Repoviva-Timestamp : unix seconds, as a decimal string
#     X-Repoviva-Signature : the hex digest above
# """

# from __future__ import annotations

# import hashlib
# import hmac
# import time

# TIMESTAMP_HEADER = "X-Repoviva-Timestamp"
# SIGNATURE_HEADER = "X-Repoviva-Signature"

# DEFAULT_MAX_SKEW_SECONDS = 300


# class SignatureError(Exception):
#     """Raised when an inbound request fails HMAC verification."""


# def _message(timestamp: int, body: bytes) -> bytes:
#     return f"{timestamp}".encode() + b"." + body


# def compute_signature(secret: str, timestamp: int, body: bytes) -> str:
#     """Return the hex HMAC-SHA256 digest for ``(timestamp, body)``."""
#     return hmac.new(secret.encode(), _message(timestamp, body), hashlib.sha256).hexdigest()


# def sign(secret: str, body: bytes, *, timestamp: int | None = None) -> dict[str, str]:
#     """Return the header dict to attach to an outbound request.

#     ``timestamp`` defaults to the current time; pass it explicitly in tests.
#     """
#     ts = int(time.time()) if timestamp is None else int(timestamp)
#     return {
#         TIMESTAMP_HEADER: str(ts),
#         SIGNATURE_HEADER: compute_signature(secret, ts, body),
#     }


# def verify(
#     secret: str,
#     body: bytes,
#     *,
#     timestamp: str | int | None,
#     signature: str | None,
#     max_skew_seconds: int = DEFAULT_MAX_SKEW_SECONDS,
#     now: int | None = None,
# ) -> None:
#     """Validate an inbound request. Returns ``None`` on success, raises otherwise.

#     Raises
#     ------
#     SignatureError
#         If a header is missing/malformed, the timestamp is outside the allowed
#         skew, or the signature does not match.
#     """
#     if not timestamp or not signature:
#         raise SignatureError("missing timestamp or signature header")

#     try:
#         ts = int(timestamp)
#     except (TypeError, ValueError) as exc:
#         raise SignatureError("malformed timestamp header") from exc

#     current = int(time.time()) if now is None else int(now)
#     if abs(current - ts) > max_skew_seconds:
#         raise SignatureError("timestamp outside allowed skew")

#     expected = compute_signature(secret, ts, body)
#     if not hmac.compare_digest(expected, signature):
#         raise SignatureError("signature mismatch")
