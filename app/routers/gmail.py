from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel

from app.core.security import create_session_cookie, load_session_cookie
from app.deps import get_current_user
from app.core.exceptions import BadRequestError
from app.models.user import User
from app.services import gmail as gmail_service

router = APIRouter()


class ConnectResponse(BaseModel):
    authorization_url: str


@router.get("/connect", response_model=ConnectResponse)
async def gmail_connect(
    redirect_uri: str | None = Query(None),
    user: User = Depends(get_current_user),
):
    """Return Google OAuth URL for the client to redirect the user to."""
    from app.core.security import get_session_serializer
    serializer = get_session_serializer()
    state = serializer.dumps({"user_id": str(user.id)}, salt="gmail-oauth-state")
    url = gmail_service.get_authorization_url(redirect_uri=redirect_uri, state=state)
    return ConnectResponse(authorization_url=url)


@router.get("/oauth/callback")
async def gmail_oauth_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    redirect: str | None = Query(None, alias="redirect"),  # frontend URL to redirect after
):
    """Google redirects here with ?code=...&state=... Exchange code and store tokens; redirect to frontend."""
    if error:
        raise BadRequestError(f"OAuth error: {error}")
    if not code or not state:
        raise BadRequestError("Missing code or state")
    from app.core.security import get_session_serializer
    serializer = get_session_serializer()
    try:
        payload = serializer.loads(state, salt="gmail-oauth-state", max_age=600)
    except Exception:
        raise BadRequestError("Invalid or expired state")
    user_id = payload.get("user_id")
    if not user_id:
        raise BadRequestError("Invalid state")
    await gmail_service.exchange_code_and_save(user_id, code)
    if redirect:
        return Response(status_code=302, headers={"Location": redirect})
    return {"status": "connected"}


@router.post("/verify")
async def gmail_verify(user: User = Depends(get_current_user)):
    """Verify stored Gmail token by calling Gmail profile."""
    from app.models.gmail_account import GmailAccount
    account = await GmailAccount.find_one(GmailAccount.user.id == user.id, GmailAccount.revoked == False)
    if not account:
        raise BadRequestError("No Gmail account connected")
    profile = await gmail_service.verify_gmail_account(account)
    return profile


@router.delete("/disconnect")
async def gmail_disconnect(user: User = Depends(get_current_user)):
    """Revoke Gmail connection for current user."""
    await gmail_service.disconnect_gmail(user.id)
    return {"status": "disconnected"}
