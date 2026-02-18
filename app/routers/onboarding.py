from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.models.user import User
from app.services import credits as credits_service
from app.workflows.onboarding_agent import run_onboarding

router = APIRouter()

ONBOARDING_BONUS_CREDITS = 50


@router.get("/status")
async def onboarding_status(user: User = Depends(get_current_user)):
    """Return onboarding state (next_step, has_gmail, has_list, has_template) from onboarding agent."""
    return await run_onboarding(str(user.id))


@router.post("/complete")
async def onboarding_complete(user: User = Depends(get_current_user)):
    """Complete onboarding; grant bonus credits once per user (idempotent)."""
    idempotency_key = f"onboarding_bonus_{user.id}"
    await credits_service.apply_ledger_entry(
        user.id,
        ONBOARDING_BONUS_CREDITS,
        "onboarding_bonus",
        reference_type="onboarding",
        reference_id=str(user.id),
        idempotency_key=idempotency_key,
    )
    return {"credits_added": ONBOARDING_BONUS_CREDITS, "status": "completed"}
