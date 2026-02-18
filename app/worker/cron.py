"""Cron: send due emails via Gmail API, rate limits."""

from datetime import datetime

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.init import init_db
from app.models.scheduled_email import ScheduledEmail
from app.services.gmail import get_valid_access_token
from app.services.rate_limit import (
    get_gmail_sent_today,
    incr_gmail_sent_today,
    gmail_daily_cap,
)
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

log = get_logger(__name__)


async def run_send_due_emails() -> None:
    """Send scheduled emails that are due (status=drafted, send_at <= now). Enforces daily cap per Gmail account."""
    await init_db()
    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        now = datetime.utcnow()
        due = await ScheduledEmail.find(
            ScheduledEmail.status == "drafted",
            ScheduledEmail.send_at <= now,
        ).limit(50).to_list()
        if due:
            log.info("send_due_emails", count=len(due))
        cap = gmail_daily_cap()
        for s in due:
            s.status = "sending"
            await s.save()
            try:
                gmail = await s.gmail_account.fetch()
                if not gmail or gmail.revoked:
                    s.status = "failed"
                    s.failure_reason = "Gmail revoked"
                    await s.save()
                    continue
                gmail_id = str(gmail.id)
                sent_today = await get_gmail_sent_today(redis, gmail_id)
                if sent_today >= cap:
                    s.status = "skipped"
                    s.failure_reason = "Daily send cap reached"
                    await s.save()
                    log.info("send_skipped_cap", gmail_account_id=gmail_id, sent_today=sent_today, cap=cap)
                    continue
                token = await get_valid_access_token(gmail)
                creds = Credentials(token=token)
                service = build("gmail", "v1", credentials=creds)
                resp = service.users().drafts().send(userId="me", body={"id": s.gmail_draft_id}).execute()
                s.status = "sent"
                s.gmail_message_id = resp.get("id", "")
                await incr_gmail_sent_today(redis, gmail_id)
            except Exception as e:
                s.status = "failed"
                s.failure_reason = str(e)[:500]
            s.updated_at = datetime.utcnow()
            await s.save()
    finally:
        await redis.aclose()
