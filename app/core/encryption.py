"""Fernet encryption for sensitive fields (e.g. Gmail tokens)."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.exceptions import BadRequestError
from app.core.logging import get_logger

log = get_logger(__name__)


def _get_fernet() -> Fernet:
    log.debug("_get_fernet")
    settings = get_settings()
    key = settings.token_encryption_key
    if not key or (isinstance(key, str) and len(key) != 44):
        # Derive from secret_key for dev when TOKEN_ENCRYPTION_KEY not set
        secret = settings.secret_key.encode()
        digest = hashlib.sha256(secret).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        raise BadRequestError(f"Invalid encryption key: {e}") from e


def encrypt_token(plain: str) -> str:
    log.debug("encrypt_token", has_plain=bool(plain))
    if not plain:
        return ""
    f = _get_fernet()
    return f.encrypt(plain.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    log.debug("decrypt_token", has_encrypted=bool(encrypted))
    if not encrypted:
        return ""
    f = _get_fernet()
    try:
        return f.decrypt(encrypted.encode()).decode()
    except InvalidToken:
        log.debug("decrypt_token_invalid")
        return ""
