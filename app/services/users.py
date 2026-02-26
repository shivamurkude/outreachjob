from datetime import datetime

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.core.config import get_settings
from app.core.exceptions import BadRequestError, UnauthorizedError
from app.core.logging import get_logger
from app.models.user import User

log = get_logger(__name__)


def verify_google_id_token(token: str) -> dict:
    """Verify Google ID token; return decoded claims (sub, email, name, picture, etc.)."""
    log.debug("verify_google_id_token")
    settings = get_settings()
    try:
        claims = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            settings.google_client_id,
        )
        return claims
    except Exception as e:
        log.warning("verify_google_id_token_failed", reason=str(e)[:100])
        raise UnauthorizedError(f"Invalid Google token: {e}") from e


async def upsert_user_from_google(claims: dict) -> User:
    log.debug("upsert_user_from_google", sub=claims.get("sub", "")[:20] if claims.get("sub") else None)
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
        # Grant signup bonus credits (idempotent by key)
        from app.services import credits as credits_service
        SIGNUP_BONUS_CREDITS = 500
        await credits_service.apply_ledger_entry(
            user.id,
            SIGNUP_BONUS_CREDITS,
            "signup",
            idempotency_key=f"signup:{user.id}",
        )
        log.info("signup_credits_granted", user_id=str(user.id), credits=SIGNUP_BONUS_CREDITS)
    return user


def session_payload_for_user(user: User) -> dict:
    log.debug("session_payload_for_user", user_id=str(user.id))
    return {"user_id": str(user.id), "session_version": user.session_version}


async def delete_user_and_all_data(user_id) -> None:
    """
    Permanently delete the user and all data linked to them.
    Caller must ensure the request is authenticated as this user.
    """
    from beanie import PydanticObjectId

    from app.models.audit_log import AuditLog
    from app.models.campaign import Campaign
    from app.models.credit_balance import CreditBalance
    from app.models.credit_ledger import CreditLedgerEntry
    from app.models.email_verification_result import EmailVerificationResult
    from app.models.enrichment_result import EnrichmentResult
    from app.models.gmail_account import GmailAccount
    from app.models.payment_order import PaymentOrder
    from app.models.recipient_item import RecipientItem
    from app.models.recipient_list import RecipientList
    from app.models.resume_document import ResumeDocument
    from app.models.scheduled_email import ScheduledEmail
    from app.models.suppression_entry import SuppressionEntry
    from app.models.template import Template

    uid = PydanticObjectId(user_id) if not isinstance(user_id, PydanticObjectId) else user_id
    user = await User.get(uid)
    if not user:
        return

    log.info("delete_user_and_all_data_start", user_id=str(uid))

    # 1. Scheduled emails (reference campaigns / gmail accounts)
    campaigns = await Campaign.find(Campaign.user.id == uid).to_list()
    campaign_ids = [c.id for c in campaigns]
    for cid in campaign_ids:
        await ScheduledEmail.find(ScheduledEmail.campaign.ref == cid).delete()

    # 2. Campaigns
    await Campaign.find(Campaign.user.id == uid).delete()

    # 3. Recipient items (reference lists)
    lists = await RecipientList.find(RecipientList.user.id == uid).to_list()
    for rlist in lists:
        await RecipientItem.find(RecipientItem.list.ref == rlist.id).delete()

    # 4. Recipient lists
    await RecipientList.find(RecipientList.user.id == uid).delete()

    # 5. Templates
    await Template.find(Template.user.id == uid).delete()

    # 6. Gmail accounts (query by ref to match stored link)
    await GmailAccount.find(GmailAccount.user.ref == uid).delete()

    # 7. Resume documents
    await ResumeDocument.find(ResumeDocument.user.id == uid).delete()

    # 8. Credit ledger & balance
    await CreditLedgerEntry.find(CreditLedgerEntry.user.ref == uid).delete()
    await CreditBalance.find(CreditBalance.user.ref == uid).delete()

    # 9. Email verification results, enrichment results
    await EmailVerificationResult.find(EmailVerificationResult.user.id == uid).delete()
    await EnrichmentResult.find(EnrichmentResult.user.id == uid).delete()

    # 10. Suppression entries (user-scoped)
    await SuppressionEntry.find(SuppressionEntry.user_id == str(uid)).delete()

    # 11. Payment orders
    await PaymentOrder.find(PaymentOrder.user.id == uid).delete()

    # 12. Audit logs
    await AuditLog.find(AuditLog.user_id == str(uid)).delete()

    # 13. User
    await user.delete()

    log.info("delete_user_and_all_data_ok", user_id=str(uid))
