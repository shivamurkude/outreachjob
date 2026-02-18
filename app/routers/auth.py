from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from app.core.security import create_session_cookie
from app.deps import SESSION_COOKIE_NAME, get_current_user
from app.models.user import User
from app.services import users as user_service

router = APIRouter()

SESSION_MAX_AGE = 7 * 24 * 3600  # 7 days


class GoogleAuthRequest(BaseModel):
    id_token: str


@router.post("/google")
async def auth_google(body: GoogleAuthRequest, response: Response):
    """Exchange Google ID token for session; set httpOnly cookie."""
    claims = user_service.verify_google_id_token(body.id_token)
    user = await user_service.upsert_user_from_google(claims)
    payload = user_service.session_payload_for_user(user)
    session_value = create_session_cookie(payload, max_age_seconds=SESSION_MAX_AGE)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_value,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=False,  # set True in prod with HTTPS
        samesite="lax",
        path="/",
    )
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
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "google_sub": user.google_sub,
    }
