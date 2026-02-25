"""Campaign preview and schedule: recipients, Gmail drafts, credit charge."""

import base64
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import Any

from beanie import PydanticObjectId
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.core.config import get_settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.logging import get_logger
from app.core.security import generate_idempotency_key
from app.models.campaign import Campaign
from app.models.gmail_account import GmailAccount
from app.models.recipient_item import RecipientItem
from app.models.recipient_list import RecipientList
from app.models.scheduled_email import ScheduledEmail
from app.models.template import Template
from app.models.user import User
from app.services import credits as credits_service
from app.services.gmail import get_valid_access_token
from app.services.templates import inject_footer

log = get_logger(__name__)


async def create_campaign(
    user_id: PydanticObjectId,
    name: str,
    template_id: PydanticObjectId,
    recipient_source: str = "list",
    recipient_list_id: str | None = None,
) -> Campaign:
    log.info("create_campaign", user_id=str(user_id), name=name, template_id=str(template_id))
    user = await User.get(user_id)
    if not user:
        raise NotFoundError("User not found")
    template = await Template.get(template_id)
    if not template or str(template.user.ref) != str(user_id):
        raise BadRequestError("Template not found")
    c = Campaign(
        user=user,
        name=name,
        template=template,
        recipient_source=recipient_source,
        recipient_list_id=recipient_list_id,
    )
    await c.insert()
    log.info("create_campaign_ok", user_id=str(user_id), campaign_id=str(c.id))
    return c


async def list_campaigns(user_id: PydanticObjectId) -> list[Campaign]:
    log.debug("list_campaigns", user_id=str(user_id))
    items = await Campaign.find(Campaign.user.id == user_id).to_list()
    log.debug("list_campaigns_ok", user_id=str(user_id), count=len(items))
    return items


async def get_campaign(campaign_id: PydanticObjectId, user_id: PydanticObjectId) -> Campaign | None:
    log.debug("get_campaign", campaign_id=str(campaign_id), user_id=str(user_id))
    c = await Campaign.find_one(
        Campaign.id == campaign_id,
        Campaign.user.id == user_id,
    )
    log.debug("get_campaign_ok", campaign_id=str(campaign_id), found=c is not None)
    return c


async def preview_campaign(
    campaign_id: PydanticObjectId,
    user_id: PydanticObjectId,
) -> dict[str, Any]:
    """Return recipient count and credit estimate for scheduling."""
    log.info("preview_campaign", campaign_id=str(campaign_id), user_id=str(user_id))
    campaign = await get_campaign(campaign_id, user_id)
    if not campaign:
        raise NotFoundError("Campaign not found")
    template = await campaign.template.fetch()
    if not template:
        raise BadRequestError("Template not found")
    if campaign.recipient_source == "list" and campaign.recipient_list_id:
        rlist = await RecipientList.get(PydanticObjectId(campaign.recipient_list_id))
        if not rlist:
            raise BadRequestError("List not found")
        list_user = await rlist.user.fetch()
        if str(list_user.id) != str(user_id):
            raise BadRequestError("List not found")
        items = await RecipientItem.find(RecipientItem.list.id == rlist.id).to_list()
        from app.services.suppression import list_suppressed_emails
        suppressed = await list_suppressed_emails(str(user_id))
        items = [i for i in items if i.email not in suppressed and ((i.chosen_email or i.email) not in suppressed)]
        count = len(items)
    else:
        count = 0
    credits_needed = count * get_settings().credits_per_send
    log.info("preview_campaign_ok", campaign_id=str(campaign_id), recipient_count=count, credits_required=credits_needed)
    return {
        "recipient_count": count,
        "credits_required": credits_needed,
        "credits_per_send": get_settings().credits_per_send,
    }


def _make_message(to: str, subject: str, body_html: str) -> dict:
    log.debug("_make_message", to=to[:50], subject=subject[:50])
    message = MIMEText(body_html, "html")
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {"raw": raw}


async def schedule_campaign(
    campaign_id: PydanticObjectId,
    user_id: PydanticObjectId,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """
    Schedule emails on Gmail only: create drafts in Gmail (OAuth) or store schedule records (app-password).
    We do not send any email; Gmail server is used for scheduling only.
    """
    log.info("schedule_campaign", campaign_id=str(campaign_id), user_id=str(user_id))
    campaign = await get_campaign(campaign_id, user_id)
    if not campaign:
        raise NotFoundError("Campaign not found")
    if campaign.status not in ("draft", "paused"):
        raise BadRequestError("Campaign cannot be scheduled in current state")
    template = await campaign.template.fetch()
    if not template:
        raise BadRequestError("Template not found")
    gmail = await GmailAccount.find_one(GmailAccount.user.id == user_id, GmailAccount.revoked == False)  # noqa: E712
    if not gmail:
        raise BadRequestError("Connect Gmail first")
    if campaign.recipient_source != "list" or not campaign.recipient_list_id:
        raise BadRequestError("Campaign has no recipient list")
    rlist = await RecipientList.get(PydanticObjectId(campaign.recipient_list_id))
    if not rlist:
        raise BadRequestError("List not found")
    if str((await rlist.user.fetch()).id) != str(user_id):
        raise BadRequestError("List not found")
    items = await RecipientItem.find(RecipientItem.list.id == rlist.id).limit(500).to_list()
    from app.services.suppression import list_suppressed_emails
    suppressed = await list_suppressed_emails(str(user_id))
    items = [i for i in items if i.email not in suppressed and ((i.chosen_email or i.email) not in suppressed)]
    if not items:
        raise BadRequestError("No recipients in list")
    key = idempotency_key or generate_idempotency_key()
    credits_needed = len(items) * get_settings().credits_per_send
    balance = await credits_service.get_balance(user_id)
    if balance < credits_needed:
        raise BadRequestError("Insufficient credits")
    await credits_service.apply_ledger_entry(
        user_id,
        -credits_needed,
        "schedule",
        reference_type="campaign",
        reference_id=str(campaign_id),
        idempotency_key=key,
    )
    body_with_footer = inject_footer(template.body_html, template.unsubscribe_footer)
    send_at = datetime.utcnow() + timedelta(minutes=1)
    created = 0
    use_smtp = getattr(gmail, "auth_type", "oauth") == "app_password"
    if use_smtp:
        # App-password accounts: no draft; store payload and send via SMTP in cron
        for item in items:
            to = item.chosen_email or item.email
            subject = template.subject
            s = ScheduledEmail(
                campaign=campaign,
                gmail_account=gmail,
                recipient_email=to,
                subject=subject,
                body_html=body_with_footer,
                send_at=send_at,
                status="drafted",
                gmail_draft_id=None,
                idempotency_key=key,
            )
            await s.insert()
            created += 1
            send_at = send_at + timedelta(seconds=30)
    else:
        # OAuth: create Gmail drafts and store draft_id
        token = await get_valid_access_token(gmail)
        creds = Credentials(token=token)
        service = build("gmail", "v1", credentials=creds)
        for item in items:
            to = item.chosen_email or item.email
            subject = template.subject
            msg = _make_message(to, subject, body_with_footer)
            try:
                draft = service.users().drafts().create(userId="me", body={"message": msg}).execute()
                draft_id = draft["id"]
            except Exception:
                continue
            s = ScheduledEmail(
                campaign=campaign,
                gmail_account=gmail,
                recipient_email=to,
                subject=subject,
                body_html=body_with_footer,
                send_at=send_at,
                status="drafted",
                gmail_draft_id=draft_id,
                idempotency_key=key,
            )
            await s.insert()
            created += 1
            send_at = send_at + timedelta(seconds=30)
    campaign.scheduled_count += created
    campaign.status = "scheduled"
    from datetime import datetime as dt
    campaign.updated_at = dt.utcnow()
    await campaign.save()
    from app.core.audit import log_event
    await log_event(str(user_id), "campaign_scheduled", "campaign", str(campaign_id), {"scheduled_count": created})
    from app.services.referrals import grant_referral_reward_if_eligible
    await grant_referral_reward_if_eligible(user_id)
    log.info("schedule_campaign_ok", campaign_id=str(campaign_id), user_id=str(user_id), scheduled=created)
    return {"scheduled": created, "idempotency_key": key}
