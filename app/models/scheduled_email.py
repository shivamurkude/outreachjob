from datetime import datetime
from typing import Literal

from beanie import Document, Link
from pydantic import Field

from app.models.campaign import Campaign
from app.models.gmail_account import GmailAccount


class ScheduledEmail(Document):
    campaign: Link[Campaign]
    gmail_account: Link[GmailAccount]
    recipient_email: str
    subject: str
    body_html: str
    send_at: datetime
    status: Literal["queued", "drafted", "sending", "sent", "failed", "skipped"] = "queued"
    gmail_draft_id: str | None = None
    gmail_message_id: str | None = None
    idempotency_key: str | None = None
    failure_reason: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "scheduled_emails"
        indexes = [
            [("send_at", 1), ("status", 1)],
            [("campaign", 1)],
            [("idempotency_key", 1)],
        ]
