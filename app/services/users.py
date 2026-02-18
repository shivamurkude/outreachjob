from datetime import datetime

from google.oauth2 import id_token
from app.core.logging import get_logger

log = get_logger(__name__)
from google.auth.transport import requests as google_requests

from app.core.config import get_settings
from app.core.exceptions import BadRequestError, UnauthorizedError
from app.core.security import create_session_cookie
from app.models.user import User


def verify_google_id_token(token: str) -> dict:
    """Verify Google ID token; return decoded claims (sub, email, name, picture, etc.)."""
    settings = get_settings()
    try:
        claims = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            settings.google_client_id,
        )
        return claims
    except Exception as e:
        raise UnauthorizedError(f"Invalid Google token: {e}") from e


async def upsert_user_from_google(claims: dict) -> User:
    google_sub = claims.get("sub")
    if not google_sub:
        raise BadRequestError("Missing sub in token")
    email = claims.get("email") or ""
    name = claims.get("name") or ""
    picture = claims.get("picture")

    user = await User.find_one(User.google_sub == google_sub)
    if user:
        user.email = email
        user.name = name
        user.picture = picture
        user.last_login_at = datetime.utcnow()
        user.updated_at = datetime.utcnow()
        await user.save()
        log.info("user_login", user_id=str(user.id), email=user.email)
        from app.core.audit import log_event
        await log_event(str(user.id), "user_login", "user", str(user.id), {"email": user.email})
    else:
        user = User(
            google_sub=google_sub,
            email=email,
            name=name,
            picture=picture,
            last_login_at=datetime.utcnow(),
        )
        await user.insert()
        log.info("user_created", user_id=str(user.id), email=user.email)
        from app.core.audit import log_event
        await log_event(str(user.id), "user_created", "user", str(user.id), {"email": user.email})
    return user


def session_payload_for_user(user: User) -> dict:
    return {"user_id": str(user.id), "session_version": user.session_version}
