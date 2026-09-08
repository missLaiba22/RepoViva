from cryptography.fernet import Fernet

from core_api.config import get_settings


def _get_fernet() -> Fernet:
    settings = get_settings()
    return Fernet(settings.token_encryption_key.encode())


def encrypt_token(plaintext: str) -> str:
    """Encrypt a GitHub OAuth token for storage in the database."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a stored GitHub OAuth token."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()