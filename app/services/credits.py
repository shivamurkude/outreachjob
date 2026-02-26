"""Credits ledger and atomic balance updates."""

from beanie import PydanticObjectId

from app.core.config import get_settings
from app.core.exceptions import BadRequestError
from app.core.logging import get_logger
from app.models.credit_balance import CreditBalance
from app.models.credit_ledger import CreditLedgerEntry
from app.models.user import User

log = get_logger(__name__)
REASONS = ("signup", "onboarding_bonus", "purchase", "schedule", "verify", "resume_scan", "refund", "referral")


async def get_balance(user_id: PydanticObjectId) -> int:
    """Return current balance for user (0 if no record)."""
    log.debug("get_balance", user_id=str(user_id))
    # Query by .ref so we match how Beanie stores Link[User]
    bal = await CreditBalance.find_one(CreditBalance.user.ref == user_id)
    out = bal.balance if bal else 0
    log.debug("get_balance_ok", user_id=str(user_id), balance=out)
    return out


async def apply_ledger_entry(
    user_id: PydanticObjectId,
    amount: int,
    reason: str,
    reference_type: str | None = None,
    reference_id: str | None = None,
    idempotency_key: str | None = None,
) -> tuple[CreditLedgerEntry, int]:
    """
    Atomically add a ledger entry and update balance.
    Returns (ledger_entry, balance_after).
    Idempotency: if idempotency_key is set and an entry already exists for this key, return existing and do not double-apply.
    """
    log.info("apply_ledger_entry", user_id=str(user_id), amount=amount, reason=reason, idempotency_key=idempotency_key)
    if reason not in REASONS:
        log.warning("apply_ledger_entry_invalid_reason", reason=reason)
        raise BadRequestError(f"Invalid reason: {reason}")
    user = await User.get(user_id)
    if not user:
        log.warning("apply_ledger_entry_user_not_found", user_id=str(user_id))
        raise BadRequestError("User not found")
    if idempotency_key:
        existing = await CreditLedgerEntry.find_one(
            CreditLedgerEntry.user.ref == user_id,
            CreditLedgerEntry.idempotency_key == idempotency_key,
        )
        if existing:
            log.info("apply_ledger_entry_idempotent_skip", user_id=str(user_id), idempotency_key=idempotency_key)
            return existing, await get_balance(user_id)

    current_balance = await get_balance(user_id)
    balance_after = current_balance + amount
    if balance_after < 0:
        log.warning("apply_ledger_entry_insufficient", user_id=str(user_id), current=current_balance, amount=amount)
        raise BadRequestError("Insufficient credits")

    balance_doc = await CreditBalance.find_one(CreditBalance.user.ref == user_id)
    if not balance_doc:
        from beanie import WriteRules
        balance_doc = CreditBalance(user=user, balance=0)
        await balance_doc.insert(link_rule=WriteRules.DO_NOTHING)
    balance_doc.balance = balance_after
    await balance_doc.save()

    entry = CreditLedgerEntry(
        user=user,
        amount=amount,
        balance_after=balance_after,
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
        idempotency_key=idempotency_key,
    )
    await entry.insert()
    log.info("apply_ledger_entry_ok", user_id=str(user_id), reason=reason, balance_after=balance_after)
    return entry, balance_after


def get_pricing():
    log.debug("get_pricing")
    s = get_settings()
    out = {
        "send": s.credits_per_send,
        "verify": s.credits_per_verify,
        "resume_scan": s.credits_per_resume_scan,
        "free_resume_scans_per_month": s.free_resume_scans_per_month,
    }
    log.debug("get_pricing_ok", **out)
    return out
