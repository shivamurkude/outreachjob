"""Admin: system recipients import and daily refresh."""

from datetime import datetime

from app.models.system_recipient import SystemRecipient

# Role-based prefixes for system recipients (same as enrichment)
ROLE_PREFIXES = ("careers", "hr", "talent", "jobs", "hiring", "recruitment")


async def import_system_recipients(
    rows: list[dict],
    source: str = "import",
    user_id: str | None = None,
) -> dict:
    """Import system recipient rows (email, domain, name, company). Dedupe by email."""
    seen = set()
    added = 0
    for row in rows:
        email = (row.get("email") or row.get("Email") or "").strip().lower()
        if not email or "@" not in email or email in seen:
            continue
        seen.add(email)
        domain = email.split("@", 1)[1]
        name = (row.get("name") or row.get("Name") or "").strip() or None
        company = (row.get("company") or row.get("Company") or "").strip() or None
        existing = await SystemRecipient.find_one(SystemRecipient.email == email)
        if existing:
            existing.domain = domain
            existing.name = name
            existing.company = company
            existing.source = source
            existing.updated_at = datetime.utcnow()
            await existing.save()
        else:
            rec = SystemRecipient(
                email=email,
                domain=domain,
                name=name,
                company=company,
                source=source,
            )
            await rec.insert()
            added += 1
    if user_id:
        from app.core.audit import log_event
        await log_event(user_id, "admin_recipients_import", "system_recipients", "", {"source": source, "imported": len(seen), "added": added})
    return {"imported": len(seen), "added": added}


async def refresh_system_recipients() -> dict:
    """Daily refresh: re-process or dedupe. Placeholder - can run import again from storage."""
    # In full impl: load from same source (e.g. S3) and re-import with source=refresh
    return {"refreshed": 0}
