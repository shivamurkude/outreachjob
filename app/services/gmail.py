"""Gmail OAuth and token lifecycle."""

from datetime import datetime, timezone

from beanie import PydanticObjectId
from google.auth.transport import requests as google_requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import get_settings
from app.core.encryption import decrypt_token, encrypt_token
from app.core.exceptions import BadRequestError, NotFoundError
from app.models.gmail_account import GmailAccount
from app.models.user import User

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


def get_oauth_flow(redirect_uri: str | None = None):
    settings = get_settings()
    redirect = redirect_uri or settings.gmail_oauth_redirect_uri
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect],
            }
        },
        scopes=GMAIL_SCOPES,
        redirect_uri=redirect,
    )


def get_authorization_url(redirect_uri: str | None = None, state: str | None = None) -> str:
    flow = get_oauth_flow(redirect_uri)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return auth_url


async def exchange_code_and_save(user_id: PydanticObjectId, code: str, redirect_uri: str | None = None) -> GmailAccount:
    flow = get_oauth_flow(redirect_uri)
    flow.fetch_token(code=code)
    credentials = flow.credentials
    account = await _store_credentials(user_id, credentials, flow.oauth2session.scope or "")
    from app.core.audit import log_event
    await log_event(str(user_id), "gmail_connected", "gmail_account", str(account.id), {"email": account.email})
    return account


async def _store_credentials(
    user_id: PydanticObjectId,
    credentials,
    scopes: str,
) -> GmailAccount:
    user = await User.get(user_id)
    if not user:
        raise NotFoundError("User not found")
    expiry = credentials.expiry if credentials.expiry else None
    existing = await GmailAccount.find_one(GmailAccount.user.id == user_id, GmailAccount.revoked == False)  # noqa: E712
    scopes_list = scopes.split() if isinstance(scopes, str) else list(scopes)
    if existing:
        existing.access_token_encrypted = encrypt_token(credentials.token or "")
        existing.refresh_token_encrypted = encrypt_token(credentials.refresh_token or existing.refresh_token_encrypted)
        existing.token_expiry = expiry
        existing.scopes = scopes_list
        existing.updated_at = datetime.utcnow()
        await existing.save()
        return existing
    # Get email from Gmail profile
    email = await _fetch_profile_email(credentials)
    acc = GmailAccount(
        user=user,
        email=email,
        access_token_encrypted=encrypt_token(credentials.token or ""),
        refresh_token_encrypted=encrypt_token(credentials.refresh_token or ""),
        token_expiry=expiry,
        scopes=scopes_list,
    )
    await acc.insert()
    return acc


async def _fetch_profile_email(credentials) -> str:
    try:
        service = build("gmail", "v1", credentials=credentials)
        profile = service.users().getProfile(userId="me").execute()
        return profile.get("emailAddress", "")
    except HttpError:
        return ""


def _credentials_from_account(account: GmailAccount):
    token = decrypt_token(account.access_token_encrypted)
    refresh = decrypt_token(account.refresh_token_encrypted)
    expiry = account.token_expiry
    return Credentials(
        token=token or None,
        refresh_token=refresh or None,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=get_settings().google_client_id,
        client_secret=get_settings().google_client_secret,
        scopes=account.scopes,
        expiry=expiry,
    )


async def refresh_access_token(account: GmailAccount) -> str:
    """Refresh access token; update account in DB; return new access token."""
    creds = _credentials_from_account(account)
    if not creds.refresh_token:
        raise BadRequestError("No refresh token")
    creds.refresh(google_requests.Request())
    account.access_token_encrypted = encrypt_token(creds.token or "")
    account.token_expiry = creds.expiry
    account.updated_at = datetime.utcnow()
    await account.save()
    return creds.token or ""


async def get_valid_access_token(account: GmailAccount) -> str:
    """Return access token, refreshing if expired (with small buffer)."""
    if account.revoked:
        raise BadRequestError("Gmail account access revoked")
    creds = _credentials_from_account(account)
    now = datetime.now(timezone.utc)
    if creds.expired or (creds.expiry and (creds.expiry.replace(tzinfo=timezone.utc) - now).total_seconds() < 60):
        return await refresh_access_token(account)
    return creds.token or ""


async def verify_gmail_account(account: GmailAccount) -> dict:
    """Call Gmail profile to verify token; return profile snippet."""
    token = await get_valid_access_token(account)
    creds = Credentials(token=token)
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    return {"email": profile.get("emailAddress"), "messagesTotal": profile.get("messagesTotal")}


async def disconnect_gmail(user_id: PydanticObjectId) -> None:
    account = await GmailAccount.find_one(GmailAccount.user.id == user_id, GmailAccount.revoked == False)  # noqa: E712
    if not account:
        raise NotFoundError("No Gmail account connected")
    account.revoked = True
    account.revoked_at = datetime.utcnow()
    account.updated_at = datetime.utcnow()
    await account.save()
    from app.core.audit import log_event
    await log_event(str(user_id), "gmail_disconnected", "gmail_account", str(account.id), {})
