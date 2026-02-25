import hashlib
import hmac
import uuid
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import get_settings
from app.core.exceptions import BadRequestError
from app.core.logging import get_logger

log = get_logger(__name__)


def get_session_serializer() -> URLSafeTimedSerializer:
    log.debug("get_session_serializer")
    settings = get_settings()
    return URLSafeTimedSerializer(
        settings.secret_key,
        salt="findmyjob-session",
        signer_kwargs={"key_derivation": "hmac", "digest_method": hashlib.sha256},
    )


def create_session_cookie(payload: dict[str, Any], max_age_seconds: int = 7 * 24 * 3600) -> str:
    """Sign payload for session cookie. Expiration is enforced when loading via max_age in loads()."""
    log.debug("create_session_cookie")
    serializer = get_session_serializer()
    return serializer.dumps(payload)


def load_session_cookie(cookie_value: str) -> dict[str, Any] | None:
    log.debug("load_session_cookie")
    serializer = get_session_serializer()
    try:
        out = serializer.loads(cookie_value, max_age=7 * 24 * 3600)
        log.debug("load_session_cookie_ok")
        return out
    except (BadSignature, SignatureExpired):
        log.debug("load_session_cookie_invalid_or_expired")
        return None


def generate_idempotency_key() -> str:
    log.debug("generate_idempotency_key")
    return str(uuid.uuid4())


def verify_razorpay_webhook(payload: bytes, signature: str, secret: str) -> bool:
    log.debug("verify_razorpay_webhook")
    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def require_idempotency_key(key: str | None) -> str:
    log.debug("require_idempotency_key", has_key=bool(key and key.strip()))
    if not key or not key.strip():
        raise BadRequestError("Idempotency-Key header is required for this request")
    return key.strip()
