from core_api.security.session_tokens import (
    generate_session_token,
    hash_session_token,
)


def test_hash_is_deterministic():
    # Creation and consumption must produce the same hash.
    assert hash_session_token("abc") == hash_session_token("abc")


def test_hash_is_64_hex_chars():
    # Must fit interviews.session_token_hash (String(64)).
    h = hash_session_token("abc")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_generated_hash_matches_raw():
    token = generate_session_token()
    assert token.hash == hash_session_token(token.raw)
    assert token.raw != token.hash


def test_tokens_are_unique():
    assert generate_session_token().raw != generate_session_token().raw