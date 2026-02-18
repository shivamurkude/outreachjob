import hashlib
import hmac
import uuid
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import get_settings
from app.core.exceptions import BadRequestError


def get_session_serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(
        settings.secret_key,
        salt="findmyjob-session",
        signer_kwargs={"key_derivation": "hmac", "digest_method": hashlib.sha256},
    )


def create_session_cookie(payload: dict[str, Any], max_age_seconds: int = 7 * 24 * 3600) -> str:
    serializer = get_session_serializer()
    return serializer.dumps(payload, max_age=max_age_seconds)


def load_session_cookie(cookie_value: str) -> dict[str, Any] | None:
    serializer = get_session_serializer()
    try:
        return serializer.loads(cookie_value, max_age=7 * 24 * 3600)
    except (BadSignature, SignatureExpired):
        return None


# Idempotency: store key -> result in Redis or Mongo; same key returns same result
def generate_idempotency_key() -> str:
    return str(uuid.uuid4())


def verify_razorpay_webhook(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def require_idempotency_key(key: str | None) -> str:
    if not key or not key.strip():
        raise BadRequestError("Idempotency-Key header is required for this request")
    return key.strip()
