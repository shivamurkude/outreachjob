from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from app.deps import get_current_user
from app.models.user import User
from app.services import campaigns as campaigns_service

router = APIRouter()


class CampaignCreate(BaseModel):
    name: str
    template_id: str
    recipient_source: str = "list"
    recipient_list_id: str | None = None


@router.get("")
async def campaigns_list(user: User = Depends(get_current_user)):
    from beanie import PydanticObjectId
    items = await campaigns_service.list_campaigns(user.id)
    return {
        "campaigns": [
            {"id": str(c.id), "name": c.name, "status": c.status, "scheduled_count": c.scheduled_count}
            for c in items
        ]
    }


@router.post("")
async def campaign_create(body: CampaignCreate, user: User = Depends(get_current_user)):
    from beanie import PydanticObjectId
    c = await campaigns_service.create_campaign(
        user.id,
        body.name,
        PydanticObjectId(body.template_id),
        recipient_source=body.recipient_source,
        recipient_list_id=body.recipient_list_id,
    )
    return {"id": str(c.id), "name": c.name, "status": c.status}


@router.get("/{campaign_id}/preview")
async def campaign_preview(
  campaign_id: str,
  user: User = Depends(get_current_user),
):
    """Preview: recipient count and credit estimate."""
    from beanie import PydanticObjectId
    out = await campaigns_service.preview_campaign(PydanticObjectId(campaign_id), user.id)
    return out


@router.get("/{campaign_id}/outreach-plan")
async def campaign_outreach_plan(campaign_id: str, user: User = Depends(get_current_user)):
    """Outreach agent: schedule plan and credit estimate for campaign (suppression applied)."""
    from app.workflows.outreach_agent import run_outreach
    return await run_outreach(campaign_id, str(user.id))


@router.post("/{campaign_id}/schedule")
async def campaign_schedule(
  campaign_id: str,
  user: User = Depends(get_current_user),
  idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    """Create Gmail drafts and schedule sends; charge credits. Optional Idempotency-Key."""
    from beanie import PydanticObjectId
    out = await campaigns_service.schedule_campaign(
        PydanticObjectId(campaign_id),
        user.id,
        idempotency_key=idempotency_key,
    )
    return out
