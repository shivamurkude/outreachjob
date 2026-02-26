"""Cron: at send_at, tell Gmail to send (drafts.send for drafts, or SMTP for queued).

Gmail API has no native 'schedule send'—drafts appear in Gmail's Drafts until we call drafts.send.
This job runs every minute and sends any scheduled email whose send_at has passed."""

from datetime import datetime, timezone

from app.core.logging import get_logger
from app.db.init import init_db
from app.models.campaign import Campaign
from app.models.scheduled_email import ScheduledEmail
from app.services.gmail import (
    get_app_password_plain,
    send_draft_via_gmail_api,
    send_email_smtp,
    send_email_via_gmail_api,
)

log = get_logger(__name__)
BATCH_SIZE = 50


async def run_send_due_emails() -> None:
    """
    Find scheduled emails with send_at <= now:
    - status=drafted and gmail_draft_id: Gmail sends the draft (drafts.send).
    - status=queued: we send via Gmail API or SMTP.
    """
    await init_db()
    now = datetime.now(timezone.utc)
    due_drafted = (
        await ScheduledEmail.find(
            ScheduledEmail.status == "drafted",
            ScheduledEmail.send_at <= now,
            ScheduledEmail.gmail_draft_id != None,  # noqa: E711
        )
        .limit(BATCH_SIZE)
        .to_list()
    )
    due_queued = (
        await ScheduledEmail.find(
            ScheduledEmail.status == "queued",
            ScheduledEmail.send_at <= now,
        )
        .limit(BATCH_SIZE)
        .to_list()
    )
    due = due_drafted + due_queued
    if not due:
        log.debug("send_due_emails", count=0)
        return
    log.info("send_due_emails", count=len(due), drafted=len(due_drafted), queued=len(due_queued))
    sent = 0
    failed = 0
    for s in due:
        s.status = "sending"
        await s.save()
        try:
            account = await s.gmail_account.fetch()
            if not account or account.revoked:
                s.status = "failed"
                s.failure_reason = "Gmail account missing or revoked"
                failed += 1
            elif s.gmail_draft_id:
                msg_id = await send_draft_via_gmail_api(account, s.gmail_draft_id)
                s.status = "sent"
                s.gmail_message_id = msg_id
                sent += 1
            elif getattr(account, "auth_type", "oauth") == "app_password":
                app_password = get_app_password_plain(account)
                send_email_smtp(
                    account.email,
                    app_password,
                    s.recipient_email,
                    s.subject,
                    s.body_html,
                )
                s.status = "sent"
                sent += 1
            else:
                msg_id = await send_email_via_gmail_api(
                    account,
                    s.recipient_email,
                    s.subject,
                    s.body_html,
                )
                s.status = "sent"
                s.gmail_message_id = msg_id
                sent += 1
        except Exception as e:
            log.warning("send_due_email_failed", scheduled_id=str(s.id), to=s.recipient_email[:50], error=str(e)[:200])
            s.status = "failed"
            s.failure_reason = str(e)[:500]
            failed += 1
        s.updated_at = datetime.now(timezone.utc)
        await s.save()

        campaign = await s.campaign.fetch()
        if campaign:
            if s.status == "sent":
                campaign.sent_count += 1
            else:
                campaign.failed_count += 1
            campaign.updated_at = datetime.now(timezone.utc)
            await campaign.save()

    log.info("send_due_emails_ok", sent=sent, failed=failed)
