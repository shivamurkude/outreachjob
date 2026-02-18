"""Enrichment: role-based email generation (careers@, hr@, etc.)."""

from beanie import PydanticObjectId

from app.core.exceptions import NotFoundError
from app.models.enrichment_result import EnrichmentResult
from app.models.recipient_item import RecipientItem
from app.models.user import User

ROLE_PREFIXES = ("careers", "hr", "talent", "jobs", "hiring", "recruitment", "recruit", "career")


def generate_role_emails(domain: str) -> list[tuple[str, str]]:
    """Return list of (email, role) for domain."""
    domain = domain.lower().strip()
    if not domain:
        return []
    return [(f"{prefix}@{domain}", prefix) for prefix in ROLE_PREFIXES]


async def enrich_bulk(
    user_id: PydanticObjectId,
    recipient_item_ids: list[PydanticObjectId],
) -> list[EnrichmentResult]:
    """
    For each recipient item (must belong to user's lists), pick first role-based email
    (e.g. careers@domain) and store. Update recipient_item.chosen_email.
    """
    user = await User.get(user_id)
    if not user:
        raise NotFoundError("User not found")
    results = []
    for rid in recipient_item_ids:
        item = await RecipientItem.get(rid)
        if not item:
            continue
        await item.fetch_link(RecipientItem.list)
        rlist = await item.list.fetch()
        if not rlist:
            continue
        list_user = await rlist.user.fetch()
        if not list_user or str(list_user.id) != str(user_id):
            continue
        domain = item.domain or (item.email.split("@", 1)[1] if "@" in item.email else "")
        candidates = generate_role_emails(domain)
        chosen = candidates[0][0] if candidates else item.email
        role = candidates[0][1] if candidates else ""
        er = EnrichmentResult(
            user=user,
            recipient_item=item,
            chosen_email=chosen,
            role=role,
        )
        await er.insert()
        item.chosen_email = chosen
        await item.save()
        results.append(er)
    return results
