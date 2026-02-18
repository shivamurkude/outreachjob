from fastapi import APIRouter, Depends, Query

from app.deps import get_current_user
from app.models.user import User
from app.services import suppression as suppression_service

router = APIRouter()


@router.get("")
async def suppressions_list(
    user: User = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List current user's suppression entries."""
    entries = await suppression_service.list_suppressions(user_id=str(user.id), limit=limit, offset=offset)
    return {
        "items": [{"email": e.email, "source": e.source, "created_at": e.created_at.isoformat()} for e in entries],
        "limit": limit,
        "offset": offset,
    }


@router.post("")
async def suppression_add(
    body: dict,
    user: User = Depends(get_current_user),
):
    """Add email to user's suppression list (manual)."""
    email = (body.get("email") or "").strip()
    if not email or "@" not in email:
        from app.core.exceptions import BadRequestError
        raise BadRequestError("Valid email required")
    await suppression_service.add_suppression(email, user_id=str(user.id), source="manual")
    return {"email": email, "status": "added"}


@router.delete("")
async def suppression_remove(
    email: str = Query(..., description="Email to remove from suppression list"),
    user: User = Depends(get_current_user),
):
    """Remove email from user's suppression list."""
    from app.models.suppression_entry import SuppressionEntry
    from app.core.exceptions import NotFoundError
    email = email.strip().lower()
    entry = await SuppressionEntry.find_one(
        SuppressionEntry.email == email,
        SuppressionEntry.user_id == str(user.id),
    )
    if not entry:
        raise NotFoundError("Suppression not found")
    await entry.delete()
    return {"email": email, "status": "removed"}
