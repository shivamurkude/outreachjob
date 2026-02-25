"""Gmail OAuth, app password, and token lifecycle."""

import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText

from beanie import PydanticObjectId
from google.auth.transport import requests as google_requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import get_settings
from app.core.encryption import decrypt_token, encrypt_token
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.logging import get_logger
from app.models.gmail_account import GmailAccount
from app.models.user import User

log = get_logger(__name__)
GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


def get_oauth_flow(redirect_uri: str | None = None):
    log.debug("get_oauth_flow", has_redirect_uri=bool(redirect_uri))
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
    log.debug("get_authorization_url")
    flow = get_oauth_flow(redirect_uri)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return auth_url


async def exchange_code_and_save(user_id: PydanticObjectId, code: str, redirect_uri: str | None = None) -> GmailAccount:
    log.info("exchange_code_and_save", user_id=str(user_id))
    flow = get_oauth_flow(redirect_uri)
    flow.fetch_token(code=code)
    credentials = flow.credentials
    account = await _store_credentials(user_id, credentials, flow.oauth2session.scope or "")
    from app.core.audit import log_event
    await log_event(str(user_id), "gmail_connected", "gmail_account", str(account.id), {"email": account.email})
    log.info("exchange_code_and_save_ok", user_id=str(user_id), account_id=str(account.id))
    return account


async def _store_credentials(
    user_id: PydanticObjectId,
    credentials,
    scopes: str,
) -> GmailAccount:
    log.debug("_store_credentials", user_id=str(user_id))
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
        log.debug("_store_credentials_updated", account_id=str(existing.id))
        return existing
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
    log.debug("_store_credentials_created", account_id=str(acc.id), email=email)
    return acc


async def _fetch_profile_email(credentials) -> str:
    log.debug("_fetch_profile_email")
    try:
        service = build("gmail", "v1", credentials=credentials)
        profile = service.users().getProfile(userId="me").execute()
        return profile.get("emailAddress", "")
    except HttpError:
        return ""


def _credentials_from_account(account: GmailAccount):
    log.debug("_credentials_from_account", account_id=str(account.id))
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
    log.debug("refresh_access_token", account_id=str(account.id))
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
    log.debug("get_valid_access_token", account_id=str(account.id))
    if account.revoked:
        raise BadRequestError("Gmail account access revoked")
    creds = _credentials_from_account(account)
    now = datetime.now(timezone.utc)
    if creds.expired or (creds.expiry and (creds.expiry.replace(tzinfo=timezone.utc) - now).total_seconds() < 60):
        return await refresh_access_token(account)
    return creds.token or ""


async def verify_gmail_account(account: GmailAccount) -> dict:
    """Call Gmail profile to verify token; return profile snippet."""
    log.info("verify_gmail_account", account_id=str(account.id))
    token = await get_valid_access_token(account)
    creds = Credentials(token=token)
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    return {"email": profile.get("emailAddress"), "messagesTotal": profile.get("messagesTotal")}


async def disconnect_gmail(user_id: PydanticObjectId) -> None:
    log.info("disconnect_gmail", user_id=str(user_id))
    account = await GmailAccount.find_one(GmailAccount.user.id == user_id, GmailAccount.revoked == False)  # noqa: E712
    if not account:
        raise NotFoundError("No Gmail account connected")
    account.revoked = True
    account.revoked_at = datetime.utcnow()
    account.updated_at = datetime.utcnow()
    await account.save()
    from app.core.audit import log_event
    await log_event(str(user_id), "gmail_disconnected", "gmail_account", str(account.id), {})


def verify_smtp_app_password(email: str, app_password: str) -> bool:
    """Verify Gmail login with app password via SMTP (STARTTLS)."""
    log.debug("verify_smtp_app_password", email=email[:50] if email else "")
    try:
        with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(email.strip(), app_password)
        log.debug("verify_smtp_app_password_ok", email=email[:50] if email else "")
        return True
    except Exception as e:
        log.warning("verify_smtp_app_password_failed", email=email[:50] if email else "", reason=str(e)[:100])
        return False


async def add_account_app_password(
    user_id: PydanticObjectId,
    email: str,
    app_password: str,
) -> GmailAccount:
    """Add a Gmail account using app password. Verifies via SMTP then stores encrypted."""
    log.info("add_account_app_password", user_id=str(user_id), email=email.strip()[:50])
    user = await User.get(user_id)
    if not user:
        raise NotFoundError("User not found")
    email = email.strip().lower()
    if not email or "@" not in email:
        raise BadRequestError("Invalid email")
    if not app_password or len(app_password.strip()) < 10:
        raise BadRequestError("Invalid app password")
    if not verify_smtp_app_password(email, app_password):
        log.warning("add_account_app_password_smtp_failed", user_id=str(user_id), email=email)
        raise BadRequestError("Could not sign in with this email and app password. Check 2FA is on and you're using an app password.")
    existing = await GmailAccount.find_one(
        GmailAccount.user.id == user_id,
        GmailAccount.email == email,
        GmailAccount.revoked == False,  # noqa: E712
    )
    if existing:
        existing.app_password_encrypted = encrypt_token(app_password)
        existing.auth_type = "app_password"
        existing.updated_at = datetime.utcnow()
        await existing.save()
        return existing
    acc = GmailAccount(
        user=user,
        email=email,
        auth_type="app_password",
        app_password_encrypted=encrypt_token(app_password),
    )
    await acc.insert()
    from app.core.audit import log_event
    await log_event(str(user_id), "gmail_connected", "gmail_account", str(acc.id), {"email": acc.email, "auth_type": "app_password"})
    log.info("add_account_app_password_ok", user_id=str(user_id), account_id=str(acc.id))
    return acc


async def list_accounts_for_user(user_id: PydanticObjectId) -> list[dict]:
    """List non-revoked Gmail accounts for user (id, email, auth_type only)."""
    log.debug("list_accounts_for_user", user_id=str(user_id))
    accounts = await GmailAccount.find(
        GmailAccount.user.id == user_id,
        GmailAccount.revoked == False,  # noqa: E712
    ).to_list()
    log.debug("list_accounts_for_user_ok", user_id=str(user_id), count=len(accounts))
    return [{"id": str(a.id), "email": a.email, "auth_type": a.auth_type} for a in accounts]


async def revoke_account_by_id(user_id: PydanticObjectId, account_id: PydanticObjectId) -> None:
    """Revoke a specific Gmail account (user must own it)."""
    log.info("revoke_account_by_id", user_id=str(user_id), account_id=str(account_id))
    account = await GmailAccount.get(account_id)
    if not account or str(account.user.ref) != str(user_id):
        raise NotFoundError("Gmail account not found")
    account.revoked = True
    account.revoked_at = datetime.utcnow()
    account.updated_at = datetime.utcnow()
    await account.save()
    from app.core.audit import log_event
    await log_event(str(user_id), "gmail_disconnected", "gmail_account", str(account.id), {})
    log.info("revoke_account_by_id_ok", user_id=str(user_id), account_id=str(account_id))


def get_app_password_plain(account: GmailAccount) -> str:
    """Decrypt app password for sending (app_password accounts only)."""
    log.debug("get_app_password_plain", account_id=str(account.id))
    if account.auth_type != "app_password":
        raise BadRequestError("Account is not an app password account")
    return decrypt_token(account.app_password_encrypted or "")


def send_email_smtp(sender_email: str, app_password: str, to: str, subject: str, body_html: str) -> None:
    """Send one email via Gmail SMTP with app password."""
    log.debug("send_email_smtp", sender=sender_email[:50], to=to[:50], subject=subject[:50])
    msg = MIMEText(body_html, "html")
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = to
    with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(sender_email, app_password)
        server.sendmail(sender_email, [to], msg.as_string())
