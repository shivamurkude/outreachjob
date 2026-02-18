from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.core.exceptions import BadRequestError
from app.deps import get_current_user
from app.models.user import User
from app.services import recipients as recipients_service
from app.worker.tasks import enqueue_process_recipient_list

router = APIRouter()


@router.post("/lists/upload")
async def lists_upload(
    user: User = Depends(get_current_user),
    name: str | None = None,
    file: UploadFile = File(...),
):
    """Upload recipients list (CSV/XLSX); creates list and enqueues processing job."""
    if not file.filename:
        raise BadRequestError("Missing filename")
    content = await file.read()
    rlist = await recipients_service.upload_list(user, name or file.filename, content, file.filename)
    try:
        await enqueue_process_recipient_list(str(rlist.id))
    except Exception:
        pass  # list stays processing; worker can be run later
    return {
        "id": str(rlist.id),
        "name": rlist.name,
        "status": rlist.status,
        "created_at": rlist.created_at.isoformat(),
    }


@router.get("/lists/{list_id}")
async def list_get(list_id: str, user: User = Depends(get_current_user)):
    """Get recipient list by id."""
    from beanie import PydanticObjectId
    rlist = await recipients_service.get_list(user.id, PydanticObjectId(list_id))
    if not rlist:
        raise BadRequestError("List not found")
    return {
        "id": str(rlist.id),
        "name": rlist.name,
        "status": rlist.status,
        "total_count": rlist.total_count,
        "valid_count": rlist.valid_count,
        "invalid_count": rlist.invalid_count,
        "created_at": rlist.created_at.isoformat(),
    }


@router.get("/lists/{list_id}/items")
async def list_items(
    list_id: str,
    user: User = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Get recipient items for a list."""
    from beanie import PydanticObjectId
    rlist = await recipients_service.get_list(user.id, PydanticObjectId(list_id))
    if not rlist:
        raise BadRequestError("List not found")
    items = await recipients_service.get_list_items(PydanticObjectId(list_id), limit=limit, offset=offset)
    return {
        "items": [
            {
                "id": str(i.id),
                "email": i.email,
                "domain": i.domain,
                "name": i.name,
                "company": i.company,
                "verification_status": i.verification_status,
            }
            for i in items
        ],
        "limit": limit,
        "offset": offset,
    }
