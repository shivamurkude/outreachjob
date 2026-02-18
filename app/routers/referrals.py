from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.deps import get_current_user
from app.models.user import User
from app.services import referrals as referrals_service

router = APIRouter()


class ApplyReferralRequest(BaseModel):
    code: str


@router.get("/me")
async def referral_me(user: User = Depends(get_current_user)):
    """Get or create my referral code."""
    code = await referrals_service.get_or_create_referral_code(user.id)
    return {"referral_code": code}


@router.post("/apply")
async def referral_apply(body: ApplyReferralRequest, user: User = Depends(get_current_user)):
    """Apply a referral code (set referred_by). Fails if invalid or already referred."""
    return await referrals_service.apply_referral_code(user.id, body.code)


@router.get("/stats")
async def referral_stats(user: User = Depends(get_current_user)):
    """Referral stats: referred_count, total_referral_credits."""
    return await referrals_service.referral_stats(user.id)
