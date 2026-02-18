"""Suppression list: add, check, list (global + per-user)."""

from beanie import PydanticObjectId

from app.models.suppression_entry import SuppressionEntry


async def add_suppression(email: str, user_id: str | None = None, source: str = "verification") -> None:
    """Add email to suppression list (idempotent). user_id=None means global."""
    email = email.strip().lower()
    if not email or "@" not in email:
        return
    existing = await SuppressionEntry.find_one(
        SuppressionEntry.email == email,
        SuppressionEntry.user_id == user_id,
    )
    if existing:
        return
    await SuppressionEntry(email=email, user_id=user_id, source=source).insert()


async def is_suppressed(email: str, user_id: str | None = None) -> bool:
    """True if email is in global list or in user's list."""
    email = email.strip().lower()
    if not email:
        return False
    # Global
    if await SuppressionEntry.find_one(SuppressionEntry.email == email, SuppressionEntry.user_id == None):
        return True
    # Per-user
    if user_id and await SuppressionEntry.find_one(SuppressionEntry.email == email, SuppressionEntry.user_id == user_id):
        return True
    return False


async def list_suppressed_emails(user_id: str | None = None) -> set[str]:
    """Return set of suppressed emails (global + user's if user_id given). For filtering in memory."""
    out: set[str] = set()
    global_entries = await SuppressionEntry.find(SuppressionEntry.user_id == None).to_list()
    out |= {e.email for e in global_entries}
    if user_id:
        user_entries = await SuppressionEntry.find(SuppressionEntry.user_id == user_id).to_list()
        out |= {e.email for e in user_entries}
    return out


async def list_suppressions(user_id: str | None = None, limit: int = 100, offset: int = 0) -> list[SuppressionEntry]:
    """List entries: global if user_id is None, else user's entries."""
    if user_id is None:
        q = SuppressionEntry.find(SuppressionEntry.user_id == None)
    else:
        q = SuppressionEntry.find(SuppressionEntry.user_id == user_id)
    return await q.skip(offset).limit(limit).to_list()
