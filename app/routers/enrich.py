from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.deps import get_current_user
from app.models.user import User
from app.services import enrichment as enrichment_service

router = APIRouter()


class EnrichBulkRequest(BaseModel):
    recipient_item_ids: list[str]


@router.post("/bulk")
async def enrich_bulk(
    body: EnrichBulkRequest,
    user: User = Depends(get_current_user),
):
    """Enrich recipient items with role-based emails (careers@, hr@, etc.)."""
    from beanie import PydanticObjectId
    ids = [PydanticObjectId(x) for x in body.recipient_item_ids]
    results = await enrichment_service.enrich_bulk(user.id, ids)
    return {
        "results": [
            {
                "recipient_item_id": str(r.recipient_item.ref),
                "chosen_email": r.chosen_email,
                "role": r.role,
            }
            for r in results
        ]
    }
