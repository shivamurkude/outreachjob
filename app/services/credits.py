"""Credits ledger and atomic balance updates."""

from beanie import PydanticObjectId

from app.core.config import get_settings
from app.core.exceptions import BadRequestError
from app.models.credit_balance import CreditBalance
from app.models.credit_ledger import CreditLedgerEntry
from app.models.user import User


REASONS = ("onboarding_bonus", "purchase", "schedule", "verify", "resume_scan", "refund", "referral")


async def get_balance(user_id: PydanticObjectId) -> int:
    """Return current balance for user (0 if no record)."""
    bal = await CreditBalance.find_one(CreditBalance.user.id == user_id)
    return bal.balance if bal else 0


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
    if reason not in REASONS:
        raise BadRequestError(f"Invalid reason: {reason}")
    user = await User.get(user_id)
    if not user:
        raise BadRequestError("User not found")
    if idempotency_key:
        existing = await CreditLedgerEntry.find_one(
            CreditLedgerEntry.user.id == user_id,
            CreditLedgerEntry.idempotency_key == idempotency_key,
        )
        if existing:
            return existing, await get_balance(user_id)

    current_balance = await get_balance(user_id)
    balance_after = current_balance + amount
    if balance_after < 0:
        raise BadRequestError("Insufficient credits")

    # Upsert balance and insert ledger in sequence (single-doc atomic for balance)
    balance_doc = await CreditBalance.find_one(CreditBalance.user.id == user_id)
    if not balance_doc:
        balance_doc = CreditBalance(user=user, balance=0)
        await balance_doc.insert()
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
    return entry, balance_after


def get_pricing():
    s = get_settings()
    return {
        "send": s.credits_per_send,
        "verify": s.credits_per_verify,
        "resume_scan": s.credits_per_resume_scan,
        "free_resume_scans_per_month": s.free_resume_scans_per_month,
    }
