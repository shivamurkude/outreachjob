from fastapi import APIRouter, Depends, Query, Response

from beanie import PydanticObjectId
from pydantic import BaseModel

from app.core.exceptions import BadRequestError
from app.core.logging import get_logger
from app.deps import get_current_user
from app.models.user import User
from app.services import gmail as gmail_service

router = APIRouter()
log = get_logger(__name__)


class ConnectResponse(BaseModel):
    authorization_url: str


class AddAccountRequest(BaseModel):
    email: str
    app_password: str


class AccountItem(BaseModel):
    id: str
    email: str
    auth_type: str


class AccountListResponse(BaseModel):
    accounts: list[AccountItem]


@router.get("/connect", response_model=ConnectResponse)
async def gmail_connect(
    redirect_uri: str | None = Query(None),
    user: User = Depends(get_current_user),
):
    """Return Google OAuth URL for the client to redirect the user to."""
    log.info("gmail_connect", user_id=str(user.id))
    from app.core.security import get_session_serializer
    serializer = get_session_serializer()
    state = serializer.dumps({"user_id": str(user.id)}, salt="gmail-oauth-state")
    url = gmail_service.get_authorization_url(redirect_uri=redirect_uri, state=state)
    return ConnectResponse(authorization_url=url)


@router.post("/accounts", response_model=AccountItem)
async def gmail_add_account(
    body: AddAccountRequest,
    user: User = Depends(get_current_user),
):
    """Add a Gmail account using email + app password (no OAuth). Supports multiple accounts."""
    log.info("gmail_add_account", user_id=str(user.id), email=body.email.strip()[:50])
    account = await gmail_service.add_account_app_password(user.id, body.email, body.app_password)
    log.info("gmail_add_account_ok", user_id=str(user.id), account_id=str(account.id), email=account.email)
    return AccountItem(id=str(account.id), email=account.email, auth_type=account.auth_type)


@router.get("/accounts", response_model=AccountListResponse)
async def gmail_list_accounts(user: User = Depends(get_current_user)):
    """List connected Gmail accounts (id, email, auth_type)."""
    log.info("gmail_list_accounts", user_id=str(user.id))
    accounts = await gmail_service.list_accounts_for_user(user.id)
    log.info("gmail_list_accounts_ok", user_id=str(user.id), count=len(accounts))
    return AccountListResponse(accounts=[AccountItem(**a) for a in accounts])


@router.delete("/accounts/{account_id}")
async def gmail_remove_account(
    account_id: str,
    user: User = Depends(get_current_user),
):
    """Remove a Gmail account by id."""
    log.info("gmail_remove_account", user_id=str(user.id), account_id=account_id)
    await gmail_service.revoke_account_by_id(user.id, PydanticObjectId(account_id))
    log.info("gmail_remove_account_ok", user_id=str(user.id), account_id=account_id)
    return {"status": "removed"}


@router.get("/oauth/callback")
async def gmail_oauth_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    redirect: str | None = Query(None, alias="redirect"),  # frontend URL to redirect after
):
    """Google redirects here with ?code=...&state=... Exchange code and store tokens; redirect to frontend."""
    log.info("gmail_oauth_callback", has_code=bool(code), has_state=bool(state), error=error)
    if error:
        log.warning("gmail_oauth_callback_error", error=error)
        raise BadRequestError(f"OAuth error: {error}")
    if not code or not state:
        log.warning("gmail_oauth_callback_missing", missing="code or state")
        raise BadRequestError("Missing code or state")
    from app.core.security import get_session_serializer
    serializer = get_session_serializer()
    try:
        payload = serializer.loads(state, salt="gmail-oauth-state", max_age=600)
    except Exception as e:
        log.warning("gmail_oauth_callback_state_invalid", reason=str(e)[:100])
        raise BadRequestError("Invalid or expired state")
    user_id = payload.get("user_id")
    if not user_id:
        raise BadRequestError("Invalid state")
    await gmail_service.exchange_code_and_save(user_id, code)
    log.info("gmail_oauth_callback_ok", user_id=user_id)
    if redirect:
        return Response(status_code=302, headers={"Location": redirect})
    return {"status": "connected"}


@router.post("/verify")
async def gmail_verify(user: User = Depends(get_current_user)):
    """Verify stored Gmail token by calling Gmail profile."""
    log.info("gmail_verify", user_id=str(user.id))
    from app.models.gmail_account import GmailAccount
    account = await GmailAccount.find_one(GmailAccount.user.id == user.id, GmailAccount.revoked == False)  # noqa: E712
    if not account:
        log.warning("gmail_verify_no_account", user_id=str(user.id))
        raise BadRequestError("No Gmail account connected")
    profile = await gmail_service.verify_gmail_account(account)
    log.info("gmail_verify_ok", user_id=str(user.id), email=profile.get("email"))
    return profile


@router.delete("/disconnect")
async def gmail_disconnect(user: User = Depends(get_current_user)):
    """Revoke Gmail connection for current user."""
    log.info("gmail_disconnect", user_id=str(user.id))
    await gmail_service.disconnect_gmail(user.id)
    log.info("gmail_disconnect_ok", user_id=str(user.id))
    return {"status": "disconnected"}
