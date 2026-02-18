"""Email verification: syntax, MX, disposable list."""

import re
from typing import Literal

import dns.resolver
from beanie import PydanticObjectId

from app.core.config import get_settings
from app.core.exceptions import BadRequestError
from app.models.email_verification_result import EmailVerificationResult
from app.models.recipient_item import RecipientItem
from app.models.user import User
from app.services import credits as credits_service

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# Minimal disposable domain list (extend in prod)
DISPOSABLE_DOMAINS = frozenset({
    "tempmail.com", "throwaway.email", "guerrillamail.com", "10minutemail.com",
    "mailinator.com", "temp-mail.org", "fakeinbox.com", "trashmail.com",
})


def check_syntax(email: str) -> bool:
    return bool(email and EMAIL_RE.match(email.strip()))


def check_mx(domain: str) -> bool:
    try:
        dns.resolver.resolve(domain, "MX")
        return True
    except Exception:
        return False


def is_disposable(domain: str) -> bool:
    return domain.lower() in DISPOSABLE_DOMAINS


def verify_single(email: str) -> Literal["valid", "invalid", "unknown", "disposable"]:
    email = email.strip().lower()
    if not check_syntax(email):
        return "invalid"
    domain = email.split("@", 1)[1]
    if is_disposable(domain):
        return "disposable"
    if not check_mx(domain):
        return "unknown"
    return "valid"


async def verify_email_for_user(
    user_id: PydanticObjectId,
    email: str,
    recipient_item_id: PydanticObjectId | None = None,
) -> EmailVerificationResult:
    """Verify one email; charge 1 credit; store result; optionally update RecipientItem."""
    balance = await credits_service.get_balance(user_id)
    if balance < get_settings().credits_per_verify:
        raise BadRequestError("Insufficient credits for verification")
    result_status = verify_single(email)
    await credits_service.apply_ledger_entry(
        user_id,
        -get_settings().credits_per_verify,
        "verify",
        reference_type="email_verification",
        reference_id=email,
    )
    user = await User.get(user_id)
    item = await RecipientItem.get(recipient_item_id) if recipient_item_id else None
    evr = EmailVerificationResult(
        user=user,
        recipient_item=item,
        email=email,
        result=result_status,
        mx_valid=check_mx(email.split("@", 1)[1] if "@" in email else ""),
        syntax_valid=check_syntax(email),
    )
    await evr.insert()
    if item:
        item.verification_status = "valid" if result_status == "valid" else "invalid"
        await item.save()
    if result_status in ("invalid", "disposable"):
        from app.services.suppression import add_suppression
        await add_suppression(email, user_id=str(user_id), source="verification")
    return evr


async def verify_bulk(
    user_id: PydanticObjectId,
    emails: list[str],
    idempotency_key: str | None = None,
) -> list[EmailVerificationResult]:
    """Verify multiple emails; charge upfront or per chunk; store results."""
    cost = len(emails) * get_settings().credits_per_verify
    balance = await credits_service.get_balance(user_id)
    if balance < cost:
        raise BadRequestError("Insufficient credits for bulk verification")
    user = await User.get(user_id)
    await credits_service.apply_ledger_entry(
        user_id,
        -cost,
        "verify",
        reference_type="bulk_verify",
        reference_id=idempotency_key or "",
        idempotency_key=idempotency_key,
    )
    results = []
    for email in emails:
        status = verify_single(email)
        domain = email.split("@", 1)[1] if "@" in email else ""
        email_lower = email.strip().lower()
        evr = EmailVerificationResult(
            user=user,
            email=email_lower,
            result=status,
            mx_valid=check_mx(domain),
            syntax_valid=check_syntax(email),
            metadata={"idempotency_key": idempotency_key} if idempotency_key else {},
        )
        await evr.insert()
        results.append(evr)
        if status in ("invalid", "disposable"):
            from app.services.suppression import add_suppression
            await add_suppression(email_lower, user_id=str(user_id), source="verification")
    return results
