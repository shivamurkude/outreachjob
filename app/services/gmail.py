"""Gmail OAuth, app password, and token lifecycle."""

import base64
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
from app.models.gmail_account import (
    GMAIL_PERSONAL_DAILY_LIMIT,
    GMAIL_WORKSPACE_DAILY_LIMIT,
    GmailAccount,
)
from app.models.user import User

log = get_logger(__name__)
GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587
# Heuristic: messagesTotal below this suggests new account
GMAIL_NEW_ACCOUNT_MESSAGES_THRESHOLD = 30

# Order must match Google token response to avoid oauthlib "scope has changed" error
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
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


def _daily_send_limit_for_email(email: str) -> int:
    """Personal @gmail.com = 500, Workspace/other = 2000."""
    if not email or "@" not in email:
        return GMAIL_PERSONAL_DAILY_LIMIT
    domain = email.split("@", 1)[1].lower()
    if domain == "gmail.com":
        return GMAIL_PERSONAL_DAILY_LIMIT
    return GMAIL_WORKSPACE_DAILY_LIMIT


async def _ensure_email_not_linked_to_other_user(email: str, current_user_id: PydanticObjectId) -> None:
    """
    Raise BadRequestError if this email is already linked to a different user.
    If the other user was deleted (orphan GmailAccount), remove the orphan and allow the link.
    """
    other = await GmailAccount.find_one(
        GmailAccount.email == email.strip().lower(),
        GmailAccount.revoked == False,  # noqa: E712
    )
    if not other:
        return
    other_user_id = other.user.ref
    if str(other_user_id) == str(current_user_id):
        return
    # Other user exists? If not (account was deleted), delete orphan and allow re-link.
    oid = getattr(other_user_id, "id", other_user_id)  # DBRef has .id
    other_user = await User.get(PydanticObjectId(oid) if not isinstance(oid, PydanticObjectId) else oid)
    if not other_user:
        log.info("gmail_orphan_removed", email=email[:50], orphan_user_id=str(other_user_id))
        await other.delete()
        return
    log.warning("email_already_linked", email=email[:50], other_user_id=str(other_user_id))
    raise BadRequestError("This email is already linked to another account.")


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
    await _ensure_email_not_linked_to_other_user(email, user_id)
    daily_limit = _daily_send_limit_for_email(email)
    acc = GmailAccount(
        user=user,
        email=email,
        access_token_encrypted=encrypt_token(credentials.token or ""),
        refresh_token_encrypted=encrypt_token(credentials.refresh_token or ""),
        token_expiry=expiry,
        scopes=scopes_list,
        daily_send_limit=daily_limit,
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
    """Call Gmail profile to verify token; return profile snippet with daily_send_limit and is_new_account."""
    log.info("verify_gmail_account", account_id=str(account.id))
    token = await get_valid_access_token(account)
    creds = Credentials(token=token)
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    messages_total = profile.get("messagesTotal") or 0
    is_new_account = messages_total < GMAIL_NEW_ACCOUNT_MESSAGES_THRESHOLD
    return {
        "email": profile.get("emailAddress"),
        "messagesTotal": messages_total,
        "daily_send_limit": getattr(account, "daily_send_limit", GMAIL_PERSONAL_DAILY_LIMIT),
        "is_new_account": is_new_account,
    }


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
    await _ensure_email_not_linked_to_other_user(email, user_id)
    existing = await GmailAccount.find_one(
        GmailAccount.user.id == user_id,
        GmailAccount.email == email,
        GmailAccount.revoked == False,  # noqa: E712
    )
    if existing:
        existing.app_password_encrypted = encrypt_token(app_password)
        existing.auth_type = "app_password"
        existing.daily_send_limit = _daily_send_limit_for_email(email)
        existing.updated_at = datetime.utcnow()
        await existing.save()
        return existing
    daily_limit = _daily_send_limit_for_email(email)
    acc = GmailAccount(
        user=user,
        email=email,
        auth_type="app_password",
        app_password_encrypted=encrypt_token(app_password),
        daily_send_limit=daily_limit,
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
    return [
        {
            "id": str(a.id),
            "email": a.email,
            "auth_type": a.auth_type,
            "daily_send_limit": getattr(a, "daily_send_limit", GMAIL_PERSONAL_DAILY_LIMIT),
        }
        for a in accounts
    ]


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


def _make_raw_message(to: str, subject: str, body_html: str, from_email: str) -> str:
    """Build RFC 2822 message and return base64url-encoded raw for Gmail API."""
    msg = MIMEText(body_html, "html")
    msg["From"] = from_email
    msg["To"] = to
    msg["Subject"] = subject
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


async def create_draft_in_gmail(account: GmailAccount, to: str, subject: str, body_html: str) -> str:
    """
    Create a draft in Gmail (OAuth only). Gmail will send it when we call drafts.send at send_at.
    Returns Gmail draft id. Raises on failure.
    """
    log.debug("create_draft_in_gmail", account_id=str(account.id), to=to[:50])
    token = await get_valid_access_token(account)
    creds = Credentials(token=token)
    service = build("gmail", "v1", credentials=creds)
    raw = _make_raw_message(to, subject, body_html, account.email)
    draft = service.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
    draft_id = draft.get("id", "")
    log.debug("create_draft_in_gmail_ok", account_id=str(account.id), draft_id=draft_id)
    return draft_id


async def send_email_via_gmail_api(account: GmailAccount, to: str, subject: str, body_html: str) -> str:
    """
    Send one email via Gmail API (OAuth). Returns Gmail message id.
    Raises on failure.
    """
    log.debug("send_email_via_gmail_api", account_id=str(account.id), to=to[:50])
    token = await get_valid_access_token(account)
    creds = Credentials(token=token)
    service = build("gmail", "v1", credentials=creds)
    raw = _make_raw_message(to, subject, body_html, account.email)
    result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    msg_id = result.get("id", "")
    log.debug("send_email_via_gmail_api_ok", account_id=str(account.id), message_id=msg_id)
    return msg_id


async def send_draft_via_gmail_api(account: GmailAccount, draft_id: str) -> str:
    """
    Send an existing Gmail draft (OAuth). Gmail server sends at call time. Returns message id.
    """
    log.debug("send_draft_via_gmail_api", account_id=str(account.id), draft_id=draft_id)
    token = await get_valid_access_token(account)
    creds = Credentials(token=token)
    service = build("gmail", "v1", credentials=creds)
    result = service.users().drafts().send(userId="me", body={"id": draft_id}).execute()
    msg_id = result.get("id", "")
    log.debug("send_draft_via_gmail_api_ok", account_id=str(account.id), message_id=msg_id)
    return msg_id


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


async def send_verification_test_email(account: GmailAccount) -> None:
    """
    Send a verification test email from the account (to itself) to confirm send permission.
    Raises BadRequestError if send fails.
    """
    log.info("send_verification_test_email", account_id=str(account.id), email=account.email[:50])
    to = account.email
    subject = "FindMyJob – Email connected"
    body_html = (
        "<p>Your email has been successfully connected to FindMyJob.</p>"
        "<p>You can now use this account to send outreach campaigns.</p>"
    )
    if account.auth_type == "app_password":
        try:
            app_password = get_app_password_plain(account)
            send_email_smtp(account.email, app_password, to, subject, body_html)
        except Exception as e:
            log.warning("send_verification_test_email_failed", account_id=str(account.id), reason=str(e)[:200])
            raise BadRequestError("Could not send test email. Check that this account has send permission.") from e
        log.info("send_verification_test_email_ok", account_id=str(account.id))
        return
    # OAuth: use Gmail API to send
    try:
        token = await get_valid_access_token(account)
        creds = Credentials(token=token)
        service = build("gmail", "v1", credentials=creds)
        msg = MIMEText(body_html, "html")
        msg["Subject"] = subject
        msg["From"] = account.email
        msg["To"] = to
        import base64
        raw = base64.urlsafe_b64encode(msg.as_string().encode()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        log.info("send_verification_test_email_ok", account_id=str(account.id))
    except Exception as e:
        log.warning("send_verification_test_email_failed", account_id=str(account.id), reason=str(e)[:200])
        raise BadRequestError("Could not send test email. Check that this account has send permission.") from e
