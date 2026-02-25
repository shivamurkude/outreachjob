"""Cron: no email sending. We only schedule emails on Gmail (create drafts); Gmail server handles send."""

from app.core.logging import get_logger
from app.db.init import init_db

log = get_logger(__name__)


async def run_send_due_emails() -> None:
    """No-op: we do not send emails from our backend. Emails are only scheduled as drafts on Gmail; the user sends or schedules them from Gmail."""
    await init_db()
    log.debug("send_due_emails_skipped", msg="Scheduling only; no send from backend")
