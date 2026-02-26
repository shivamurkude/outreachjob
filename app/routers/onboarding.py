from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.exceptions import BadRequestError
from app.core.logging import get_logger
from app.deps import get_current_user
from app.models.user import User
from app.workflows.onboarding_agent import run_onboarding

router = APIRouter()
log = get_logger(__name__)


class AttestRequest(BaseModel):
    terms_accepted: bool
    privacy_accepted: bool
    outreach_consent: bool
    timezone: str = "UTC"
    locale: str = "en"


@router.get("/status")
async def onboarding_status(user: User = Depends(get_current_user)):
    """Return onboarding state (next_step, has_gmail, has_list, has_template, has_launched_campaign, completed)."""
    log.info("onboarding_status", user_id=str(user.id))
    out = await run_onboarding(str(user.id))
    log.info("onboarding_status_ok", user_id=str(user.id), next_step=out.get("next_step"), completed=out.get("completed"))
    return out


@router.post("/attest")
async def onboarding_attest(body: AttestRequest, user: User = Depends(get_current_user)):
    """Record compliance: terms, privacy, lawful outreach consent. Idempotent if already attested."""
    if not body.terms_accepted or not body.privacy_accepted or not body.outreach_consent:
        raise BadRequestError("Terms, privacy, and outreach consent must be accepted")
    if user.attested_outreach_allowed:
        log.info("onboarding_attest_already", user_id=str(user.id))
        return {"status": "already_attested", "attested_at": user.attested_at.isoformat() if user.attested_at else None}
    user.attested_outreach_allowed = True
    user.attested_at = datetime.utcnow()
    user.timezone = body.timezone or user.timezone
    user.locale = body.locale or user.locale
    user.updated_at = datetime.utcnow()
    await user.save()
    log.info("onboarding_attest_ok", user_id=str(user.id))
    return {"status": "attested", "attested_at": user.attested_at.isoformat()}


@router.post("/complete")
async def onboarding_complete(user: User = Depends(get_current_user)):
    """Legacy: onboarding completion and bonus are now applied on first campaign schedule. Returns status only."""
    log.info("onboarding_complete", user_id=str(user.id))
    out = await run_onboarding(str(user.id))
    if out.get("completed"):
        return {"status": "completed", "credits_added": 0}
    return {"status": "incomplete", "next_step": out.get("next_step")}
