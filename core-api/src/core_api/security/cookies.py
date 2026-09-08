from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from core_api.config import get_settings

# Different "salts" so a state cookie can never be misread as a session cookie
# even though both use the same underlying secret.
STATE_SALT = "oauth-state"
SESSION_SALT = "session"

STATE_MAX_AGE_SECONDS = 10 * 60          # 10 minutes
SESSION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60  # 7 days


def _serializer(salt: str) -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.cookie_secret, salt=salt)


def sign_state(state_value: str) -> str:
    return _serializer(STATE_SALT).dumps(state_value)


def read_state(signed_value: str) -> str | None:
    """Return the state if valid and unexpired; None otherwise."""
    try:
        return _serializer(STATE_SALT).loads(
            signed_value, max_age=STATE_MAX_AGE_SECONDS
        )
    except (BadSignature, SignatureExpired):
        return None


def sign_session(user_id: int) -> str:
    return _serializer(SESSION_SALT).dumps(user_id)


def read_session(signed_value: str) -> int | None:
    """Return the user id if valid and unexpired; None otherwise."""
    try:
        return _serializer(SESSION_SALT).loads(
            signed_value, max_age=SESSION_MAX_AGE_SECONDS
        )
    except (BadSignature, SignatureExpired):
        return None