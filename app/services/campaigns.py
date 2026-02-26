"""Campaign preview and schedule: create emails in Gmail (drafts), schedule at random time; Gmail sends at send_at."""

import random
from datetime import datetime, timedelta, timezone
from typing import Any

from beanie import PydanticObjectId

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
from app.services.gmail import create_draft_in_gmail
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
    template = await Template.find_one(
        Template.id == template_id,
        Template.user.id == user_id,
    )
    if not template:
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


async def get_campaign_detail(campaign_id: PydanticObjectId, user_id: PydanticObjectId) -> dict[str, Any]:
    """Return full campaign details for the detail page."""
    campaign = await get_campaign(campaign_id, user_id)
    if not campaign:
        raise NotFoundError("Campaign not found")
    template = await campaign.template.fetch()
    list_name: str | None = None
    if campaign.recipient_list_id:
        rlist = await RecipientList.get(PydanticObjectId(campaign.recipient_list_id))
        if rlist:
            list_name = rlist.name
    return {
        "id": str(campaign.id),
        "name": campaign.name,
        "status": campaign.status,
        "scheduling_status": getattr(campaign, "scheduling_status", "idle"),
        "scheduling_total": getattr(campaign, "scheduling_total", 0),
        "template": {
            "id": str(template.id) if template else None,
            "name": getattr(template, "name", None) if template else None,
            "subject": getattr(template, "subject", None) if template else None,
        },
        "recipient_list_id": campaign.recipient_list_id,
        "recipient_list_name": list_name,
        "scheduled_count": campaign.scheduled_count,
        "sent_count": campaign.sent_count,
        "failed_count": campaign.failed_count,
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        "updated_at": campaign.updated_at.isoformat() if campaign.updated_at else None,
    }


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

    # Gmail quota and rate-density for frontend
    gmail = await GmailAccount.find_one(GmailAccount.user.id == user_id, GmailAccount.revoked == False)  # noqa: E712
    daily_send_limit = getattr(gmail, "daily_send_limit", 500) if gmail else 500
    emails_per_day = count  # single-day schedule; could be split over days later
    within_daily_limit = emails_per_day <= daily_send_limit
    rate_density_warning = count > 100  # 100+ in short window

    return {
        "recipient_count": count,
        "credits_required": credits_needed,
        "credits_per_send": get_settings().credits_per_send,
        "daily_send_limit": daily_send_limit,
        "within_daily_limit": within_daily_limit,
        "rate_density_warning": rate_density_warning,
    }


async def schedule_campaign(
    campaign_id: PydanticObjectId,
    user_id: PydanticObjectId,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """
    Start background scheduling: charge credits, set scheduling_status=in_progress, enqueue job.
    Job creates each email in Gmail (draft) with random send_at; at send_at cron tells Gmail to send the draft.
    Returns immediately with scheduling_status, scheduled_count, scheduling_total for polling.
    """
    log.info("schedule_campaign", campaign_id=str(campaign_id), user_id=str(user_id))
    campaign = await get_campaign(campaign_id, user_id)
    if not campaign:
        raise NotFoundError("Campaign not found")
    if campaign.status not in ("draft", "paused"):
        raise BadRequestError("Campaign cannot be scheduled in current state")
    if getattr(campaign, "scheduling_status", "idle") == "in_progress":
        return {
            "scheduling_status": "in_progress",
            "scheduled_count": campaign.scheduled_count,
            "scheduling_total": getattr(campaign, "scheduling_total", 0),
            "idempotency_key": idempotency_key,
        }
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
    daily_send_limit = getattr(gmail, "daily_send_limit", 500)
    if len(items) > daily_send_limit:
        raise BadRequestError(
            f"Cannot schedule {len(items)} emails: Gmail daily limit is {daily_send_limit}. "
            "Split your campaign or add more sending accounts."
        )
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
    campaign.scheduling_status = "in_progress"
    campaign.scheduling_total = len(items)
    campaign.scheduled_count = 0
    campaign.updated_at = datetime.now(timezone.utc)
    await campaign.save()

    if get_settings().run_schedule_in_process:
        log.info("schedule_campaign_in_process", campaign_id=str(campaign_id), total=len(items))
        await run_schedule_campaign_background(str(campaign_id), str(user_id), key)
        campaign = await get_campaign(campaign_id, user_id)
        return {
            "scheduling_status": campaign.scheduling_status if campaign else "completed",
            "scheduled_count": campaign.scheduled_count if campaign else len(items),
            "scheduling_total": len(items),
            "idempotency_key": key,
        }
    from app.worker.tasks import enqueue_schedule_campaign  # avoid circular import at module load
    try:
        await enqueue_schedule_campaign(str(campaign_id), str(user_id), key)
    except Exception as e:
        log.warning("schedule_campaign_enqueue_failed", campaign_id=str(campaign_id), error=str(e)[:200])
        campaign.scheduling_status = "idle"
        campaign.scheduling_total = 0
        campaign.updated_at = datetime.utcnow()
        await campaign.save()
        raise BadRequestError(
            "Could not queue scheduling. Is Redis running and REDIS_URL set? Start the Worker (ARQ) to process jobs."
        ) from e

    log.info("schedule_campaign_started", campaign_id=str(campaign_id), user_id=str(user_id), total=len(items))
    return {
        "scheduling_status": "in_progress",
        "scheduled_count": 0,
        "scheduling_total": len(items),
        "idempotency_key": key,
    }


async def run_schedule_campaign_background(campaign_id_str: str, user_id_str: str, idempotency_key: str) -> None:
    """
    Background job: create each email in Gmail (draft for OAuth, or queued for app_password) with random send_at.
    Gmail will send drafts when cron calls drafts.send at send_at.
    """
    campaign_id = PydanticObjectId(campaign_id_str)
    user_id = PydanticObjectId(user_id_str)
    log.info("run_schedule_campaign_background", campaign_id=campaign_id_str, user_id=user_id_str)
    campaign = await get_campaign(campaign_id, user_id)
    if not campaign or getattr(campaign, "scheduling_status", "idle") != "in_progress":
        log.warning("run_schedule_campaign_background_skip", campaign_id=campaign_id_str)
        return
    template = await campaign.template.fetch()
    if not template:
        return
    gmail = await GmailAccount.find_one(GmailAccount.user.id == user_id, GmailAccount.revoked == False)  # noqa: E712
    if not gmail:
        return
    rlist = await RecipientList.get(PydanticObjectId(campaign.recipient_list_id))
    if not rlist:
        return
    items = await RecipientItem.find(RecipientItem.list.id == rlist.id).limit(500).to_list()
    from app.services.suppression import list_suppressed_emails
    suppressed = await list_suppressed_emails(str(user_id))
    items = [i for i in items if i.email not in suppressed and ((i.chosen_email or i.email) not in suppressed)]
    body_with_footer = inject_footer(template.body_html, template.unsubscribe_footer)
    now = datetime.now(timezone.utc)
    min_delay_seconds = 60
    max_delay_seconds = 48 * 3600
    use_oauth = getattr(gmail, "auth_type", "oauth") != "app_password"
    created = 0
    for item in items:
        to = item.chosen_email or item.email
        subject = template.subject
        send_at = now + timedelta(seconds=random.uniform(min_delay_seconds, max_delay_seconds))
        draft_id = None
        status = "queued"
        if use_oauth:
            try:
                draft_id = await create_draft_in_gmail(gmail, to, subject, body_with_footer)
                status = "drafted"
            except Exception as e:
                log.warning("schedule_campaign_draft_failed", to=to[:50], error=str(e)[:200])
                continue
        s = ScheduledEmail(
            campaign=campaign,
            gmail_account=gmail,
            recipient_email=to,
            subject=subject,
            body_html=body_with_footer,
            send_at=send_at,
            status=status,
            gmail_draft_id=draft_id,
            idempotency_key=idempotency_key,
        )
        await s.insert()
        created += 1
        campaign.scheduled_count = created
        campaign.updated_at = datetime.now(timezone.utc)
        await campaign.save()

    campaign.scheduling_status = "completed"
    campaign.status = "scheduled"
    campaign.updated_at = datetime.now(timezone.utc)
    await campaign.save()
    from app.core.audit import log_event
    await log_event(str(user_id), "campaign_scheduled", "campaign", str(campaign_id), {"scheduled_count": created})
    from app.services.referrals import grant_referral_reward_if_eligible
    await grant_referral_reward_if_eligible(user_id)
    user = await User.get(user_id)
    if user and user.onboarding_completed_at is None:
        user.onboarding_completed_at = datetime.now(timezone.utc)
        user.updated_at = datetime.now(timezone.utc)
        await user.save()
        ONBOARDING_BONUS_CREDITS = 50
        await credits_service.apply_ledger_entry(
            user_id,
            ONBOARDING_BONUS_CREDITS,
            "onboarding_bonus",
            reference_type="onboarding",
            reference_id=str(user_id),
            idempotency_key=f"onboarding_bonus_{user_id}",
        )
        log.info("onboarding_completed_on_first_schedule", user_id=str(user_id), credits_added=ONBOARDING_BONUS_CREDITS)
    log.info("run_schedule_campaign_background_ok", campaign_id=campaign_id_str, scheduled=created)
