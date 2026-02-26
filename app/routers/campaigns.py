from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from app.core.logging import get_logger
from app.deps import get_current_user
from app.models.user import User
from app.services import campaigns as campaigns_service

router = APIRouter()
log = get_logger(__name__)


class CampaignCreate(BaseModel):
    name: str
    template_id: str
    recipient_source: str = "list"
    recipient_list_id: str | None = None


@router.get("")
async def campaigns_list(user: User = Depends(get_current_user)):
    log.info("campaigns_list", user_id=str(user.id))
    items = await campaigns_service.list_campaigns(user.id)
    log.info("campaigns_list_ok", user_id=str(user.id), count=len(items))
    return {
        "campaigns": [
            {"id": str(c.id), "name": c.name, "status": c.status, "scheduled_count": c.scheduled_count}
            for c in items
        ]
    }


@router.get("/{campaign_id}")
async def campaign_detail(campaign_id: str, user: User = Depends(get_current_user)):
    """Return full campaign details (template, list name, counts, etc.)."""
    log.info("campaign_detail", user_id=str(user.id), campaign_id=campaign_id)
    from beanie import PydanticObjectId
    out = await campaigns_service.get_campaign_detail(PydanticObjectId(campaign_id), user.id)
    log.info("campaign_detail_ok", user_id=str(user.id), campaign_id=campaign_id)
    return out


@router.post("")
async def campaign_create(body: CampaignCreate, user: User = Depends(get_current_user)):
    log.info("campaign_create", user_id=str(user.id), name=body.name, template_id=body.template_id)
    from beanie import PydanticObjectId
    c = await campaigns_service.create_campaign(
        user.id,
        body.name,
        PydanticObjectId(body.template_id),
        recipient_source=body.recipient_source,
        recipient_list_id=body.recipient_list_id,
    )
    log.info("campaign_create_ok", user_id=str(user.id), campaign_id=str(c.id))
    return {"id": str(c.id), "name": c.name, "status": c.status}


@router.get("/{campaign_id}/preview")
async def campaign_preview(
  campaign_id: str,
  user: User = Depends(get_current_user),
):
    """Preview: recipient count and credit estimate."""
    log.info("campaign_preview", user_id=str(user.id), campaign_id=campaign_id)
    from beanie import PydanticObjectId
    out = await campaigns_service.preview_campaign(PydanticObjectId(campaign_id), user.id)
    log.info("campaign_preview_ok", user_id=str(user.id), campaign_id=campaign_id, recipient_count=out.get("recipient_count"))
    return out


@router.get("/{campaign_id}/outreach-plan")
async def campaign_outreach_plan(campaign_id: str, user: User = Depends(get_current_user)):
    """Outreach agent: schedule plan and credit estimate for campaign (suppression applied)."""
    log.info("campaign_outreach_plan", user_id=str(user.id), campaign_id=campaign_id)
    from app.workflows.outreach_agent import run_outreach
    return await run_outreach(campaign_id, str(user.id))


@router.post("/{campaign_id}/schedule")
async def campaign_schedule(
  campaign_id: str,
  user: User = Depends(get_current_user),
  idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    """Start background scheduling: create emails in Gmail at random times; returns 202 for polling."""
    log.info("campaign_schedule", user_id=str(user.id), campaign_id=campaign_id)
    from beanie import PydanticObjectId
    out = await campaigns_service.schedule_campaign(
        PydanticObjectId(campaign_id),
        user.id,
        idempotency_key=idempotency_key,
    )
    log.info(
        "campaign_schedule_ok",
        user_id=str(user.id),
        campaign_id=campaign_id,
        scheduling_status=out.get("scheduling_status"),
        scheduled_count=out.get("scheduled_count"),
        scheduling_total=out.get("scheduling_total"),
    )
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=202, content=out)
