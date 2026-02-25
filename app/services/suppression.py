"""Suppression list: add, check, list (global + per-user)."""

from app.core.logging import get_logger
from app.models.suppression_entry import SuppressionEntry

log = get_logger(__name__)


async def add_suppression(email: str, user_id: str | None = None, source: str = "verification") -> None:
    """Add email to suppression list (idempotent). user_id=None means global."""
    log.debug("add_suppression", email=email[:50] if email else "", user_id=user_id, source=source)
    email = email.strip().lower()
    if not email or "@" not in email:
        return
    existing = await SuppressionEntry.find_one(
        SuppressionEntry.email == email,
        SuppressionEntry.user_id == user_id,
    )
    if existing:
        log.debug("add_suppression_exists")
        return
    await SuppressionEntry(email=email, user_id=user_id, source=source).insert()
    log.debug("add_suppression_ok", email=email[:50])


async def is_suppressed(email: str, user_id: str | None = None) -> bool:
    """True if email is in global list or in user's list."""
    log.debug("is_suppressed", email=email[:50] if email else "", user_id=user_id)
    email = email.strip().lower()
    if not email:
        return False
    # Global
    if await SuppressionEntry.find_one(SuppressionEntry.email == email, SuppressionEntry.user_id == None):  # noqa: E711
        log.debug("is_suppressed_ok", result=True, scope="global")
        return True
    # Per-user
    if user_id and await SuppressionEntry.find_one(SuppressionEntry.email == email, SuppressionEntry.user_id == user_id):
        log.debug("is_suppressed_ok", result=True, scope="user")
        return True
    log.debug("is_suppressed_ok", result=False)
    return False


async def list_suppressed_emails(user_id: str | None = None) -> set[str]:
    """Return set of suppressed emails (global + user's if user_id given). For filtering in memory."""
    log.debug("list_suppressed_emails", user_id=user_id)
    out: set[str] = set()
    global_entries = await SuppressionEntry.find(SuppressionEntry.user_id == None).to_list()  # noqa: E711
    out |= {e.email for e in global_entries}
    if user_id:
        user_entries = await SuppressionEntry.find(SuppressionEntry.user_id == user_id).to_list()
        out |= {e.email for e in user_entries}
    log.debug("list_suppressed_emails_ok", count=len(out))
    return out


async def list_suppressions(user_id: str | None = None, limit: int = 100, offset: int = 0) -> list[SuppressionEntry]:
    """List entries: global if user_id is None, else user's entries."""
    log.debug("list_suppressions", user_id=user_id, limit=limit, offset=offset)
    if user_id is None:
        q = SuppressionEntry.find(SuppressionEntry.user_id == None)  # noqa: E711
    else:
        q = SuppressionEntry.find(SuppressionEntry.user_id == user_id)
    items = await q.skip(offset).limit(limit).to_list()
    log.debug("list_suppressions_ok", count=len(items))
    return items
