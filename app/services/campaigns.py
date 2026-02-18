"""Campaign preview and schedule: recipients, Gmail drafts, credit charge."""

from datetime import datetime, timedelta
from typing import Any

from beanie import PydanticObjectId

from app.core.config import get_settings
from app.core.exceptions import BadRequestError, NotFoundError
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

import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


async def create_campaign(
    user_id: PydanticObjectId,
    name: str,
    template_id: PydanticObjectId,
    recipient_source: str = "list",
    recipient_list_id: str | None = None,
) -> Campaign:
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
    return c


async def list_campaigns(user_id: PydanticObjectId) -> list[Campaign]:
    return await Campaign.find(Campaign.user.id == user_id).to_list()


async def get_campaign(campaign_id: PydanticObjectId, user_id: PydanticObjectId) -> Campaign | None:
    return await Campaign.find_one(
        Campaign.id == campaign_id,
        Campaign.user.id == user_id,
    )


async def preview_campaign(
    campaign_id: PydanticObjectId,
    user_id: PydanticObjectId,
) -> dict[str, Any]:
    """Return recipient count and credit estimate for scheduling."""
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
    return {
        "recipient_count": count,
        "credits_required": credits_needed,
        "credits_per_send": get_settings().credits_per_send,
    }


def _make_message(to: str, subject: str, body_html: str) -> dict:
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
    Create Gmail drafts for each recipient, create ScheduledEmail records,
    charge credits. Worker will send at send_at via Gmail API.
    """
    campaign = await get_campaign(campaign_id, user_id)
    if not campaign:
        raise NotFoundError("Campaign not found")
    if campaign.status not in ("draft", "paused"):
        raise BadRequestError("Campaign cannot be scheduled in current state")
    template = await campaign.template.fetch()
    if not template:
        raise BadRequestError("Template not found")
    gmail = await GmailAccount.find_one(GmailAccount.user.id == user_id, GmailAccount.revoked == False)
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
    user = await User.get(user_id)
    token = await get_valid_access_token(gmail)
    creds = Credentials(token=token)
    service = build("gmail", "v1", credentials=creds)
    body_with_footer = inject_footer(template.body_html, template.unsubscribe_footer)
    send_at = datetime.utcnow() + timedelta(minutes=1)
    created = 0
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
    return {"scheduled": created, "idempotency_key": key}
