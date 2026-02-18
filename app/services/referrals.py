"""Referral codes and reward ledger entries."""

from beanie import PydanticObjectId

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.user import User
from app.services import credits as credits_service

REFERRAL_REWARD_CREDITS = 25


async def get_or_create_referral_code(user_id: PydanticObjectId) -> str:
    """Return user's referral code; generate and save if missing."""
    user = await User.get(user_id)
    if not user:
        raise NotFoundError("User not found")
    if user.referral_code:
        return user.referral_code
    for _ in range(10):
        code = _generate_code()
        existing = await User.find_one(User.referral_code == code)
        if not existing:
            user.referral_code = code
            await user.save()
            return code
    raise BadRequestError("Could not generate unique referral code")


def _generate_code() -> str:
    import secrets
    return secrets.token_urlsafe(6).upper().replace("-", "").replace("_", "")[:10]


async def apply_referral_code(user_id: PydanticObjectId, code: str) -> dict:
    """Apply a referral code to current user (set referred_by). Idempotent: no-op if already referred."""
    user = await User.get(user_id)
    if not user:
        raise NotFoundError("User not found")
    code = (code or "").strip().upper()
    if not code:
        raise BadRequestError("Referral code required")
    referrer = await User.find_one(User.referral_code == code)
    if not referrer:
        raise NotFoundError("Invalid referral code")
    if str(referrer.id) == str(user_id):
        raise BadRequestError("Cannot use your own referral code")
    if user.referred_by is not None:
        return {"status": "already_referred", "message": "You have already used a referral code"}
    user.referred_by = referrer
    await user.save()
    return {"status": "applied", "message": "Referral code applied"}


async def grant_referral_reward_if_eligible(referee_id: PydanticObjectId) -> None:
    """
    If referee was referred and referrer has not yet been rewarded for this referee,
    credit referrer with REFERRAL_REWARD_CREDITS. Call after referee's first purchase or first schedule.
    """
    referee = await User.get(referee_id)
    if not referee or referee.referred_by is None:
        return
    referrer = await referee.referred_by.fetch()
    if not referrer:
        return
    from app.models.credit_ledger import CreditLedgerEntry
    idempotency_key = f"referral_reward_{referee_id}"
    existing = await CreditLedgerEntry.find_one(
        CreditLedgerEntry.user.id == referrer.id,
        CreditLedgerEntry.idempotency_key == idempotency_key,
    )
    if existing:
        return
    await credits_service.apply_ledger_entry(
        referrer.id,
        REFERRAL_REWARD_CREDITS,
        "referral",
        reference_type="referral_reward",
        reference_id=str(referee_id),
        idempotency_key=idempotency_key,
    )


async def referral_stats(user_id: PydanticObjectId) -> dict:
    """Return count of users referred and total referral rewards received."""
    user = await User.get(user_id)
    if not user:
        raise NotFoundError("User not found")
    referred_count = await User.find(User.referred_by.ref == user.id).count()
    from app.models.credit_ledger import CreditLedgerEntry
    reward_entries = await CreditLedgerEntry.find(
        CreditLedgerEntry.user.id == user.id,
        CreditLedgerEntry.reason == "referral",
    ).to_list()
    total_reward = sum(e.amount for e in reward_entries)
    return {"referred_count": referred_count, "total_referral_credits": total_reward}
