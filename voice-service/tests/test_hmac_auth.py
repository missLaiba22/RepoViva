import hashlib
import hmac

from voice_service.internal.hmac_auth import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign


def test_sign_matches_wire_format():
    """Recompute the signature the way Core API's verifier does (decision 027)."""
    body = b'{"token":"abc"}'
    headers = sign(body=body, secret="s3cret", timestamp=1_700_000_000)

    expected = hmac.new(b"s3cret", b"1700000000." + body, hashlib.sha256).hexdigest()
    assert headers[TIMESTAMP_HEADER] == "1700000000"
    assert headers[SIGNATURE_HEADER] == f"sha256={expected}"
