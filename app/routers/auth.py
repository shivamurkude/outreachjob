from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import create_session_cookie
from app.deps import SESSION_COOKIE_NAME, get_current_user
from app.models.user import User
from app.services import users as user_service

router = APIRouter()
settings = get_settings()
log = get_logger(__name__)

SESSION_MAX_AGE = 7 * 24 * 3600  # 7 days
# Use secure cookie when not in development (staging/prod use HTTPS)
SECURE_COOKIE = settings.env != "development"


class GoogleAuthRequest(BaseModel):
    id_token: str


@router.post("/google")
async def auth_google(body: GoogleAuthRequest, response: Response):
    """Exchange Google ID token for session; set httpOnly cookie."""
    log.info("auth_google_start")
    claims = user_service.verify_google_id_token(body.id_token)
    user = await user_service.upsert_user_from_google(claims)
    payload = user_service.session_payload_for_user(user)
    session_value = create_session_cookie(payload, max_age_seconds=SESSION_MAX_AGE)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_value,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=SECURE_COOKIE,
        samesite="lax",
        path="/",
    )
    log.info("auth_google_ok", user_id=str(user.id), email=user.email)
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "picture": user.picture,
        }
    }


@router.get("/me")
async def auth_me(user: User = Depends(get_current_user)):
    """Return current user. Requires session cookie."""
    log.info("auth_me_ok", user_id=str(user.id))
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "avatar_url": user.picture,
        "google_sub": user.google_sub,
        "attested_outreach_allowed": getattr(user, "attested_outreach_allowed", False),
        "timezone": getattr(user, "timezone", "UTC"),
        "locale": getattr(user, "locale", "en"),
    }


class DeleteAccountRequest(BaseModel):
    confirm: bool = False


@router.post("/delete-account")
async def auth_delete_account(body: DeleteAccountRequest, response: Response, user: User = Depends(get_current_user)):
    """
    Permanently delete the current user and all their data (campaigns, templates,
    lists, credits, Gmail accounts, resume, audit logs, etc.). Requires confirm=true.
    """
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to delete your account.")
    log.info("auth_delete_account", user_id=str(user.id), email=user.email[:50] if user.email else None)
    await user_service.delete_user_and_all_data(user.id)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
    )
    return {"status": "ok", "message": "Account and all data deleted."}


@router.post("/logout")
async def auth_logout(response: Response):
    """Clear session cookie (log user out)."""
    log.info("auth_logout")
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
    )
    return {"status": "ok"}
