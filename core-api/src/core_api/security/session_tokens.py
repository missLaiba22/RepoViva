"""One-time interview session tokens (decision 035).

The raw token goes to the client once and is never stored; Core API
stores only its SHA-256 hash. This module only creates and hashes
secrets. How long a token lives is an interview rule, not a property of
the token, so expiry belongs in interviews/service.py.
"""

import hashlib
import secrets
from typing import NamedTuple

# 32 random bytes = 256 bits. Python's `secrets` docs consider 32 bytes
# sufficient for typical security tokens. token_urlsafe encodes them as
# ~43 URL-safe characters.
_TOKEN_BYTES = 32


class SessionToken(NamedTuple):
    """A freshly generated token and its hash.

    Named fields, not a plain tuple: both values are str, so a swapped
    unpacking order would silently store the raw token in the database.
    """

    raw: str  # returned to the client once; never persisted
    hash: str  # stored in interviews.session_token_hash


def hash_session_token(raw: str) -> str:
    """Return the hex-encoded SHA-256 of a raw token (always 64 chars).

    The single place where a token is encoded and hashed. Used both when
    the interview is created and when Voice Service's consume call
    arrives, so the two paths cannot hash differently.

    A fast hash is safe here, unlike for passwords: the input has 256 bits
    of randomness, so it cannot be brute-forced. Being deterministic (no
    salt), the hash can also be looked up directly in the database.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_session_token() -> SessionToken:
    """Create a new random token and its hash."""
    raw = secrets.token_urlsafe(_TOKEN_BYTES)
    return SessionToken(raw=raw, hash=hash_session_token(raw))