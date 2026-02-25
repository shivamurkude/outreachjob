from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.core.exceptions import BadRequestError
from app.core.logging import get_logger
from app.deps import get_current_user
from app.models.user import User
from app.services import recipients as recipients_service
from app.worker.tasks import enqueue_process_recipient_list

router = APIRouter()
log = get_logger(__name__)


@router.get("/lists")
async def lists_list(user: User = Depends(get_current_user)):
    """List recipient lists for current user."""
    log.info("lists_list", user_id=str(user.id))
    from app.models.recipient_list import RecipientList
    items = await RecipientList.find(RecipientList.user.id == user.id).sort(-RecipientList.created_at).to_list()
    log.info("lists_list_ok", user_id=str(user.id), count=len(items))
    return {
        "lists": [
            {
                "id": str(r.id),
                "name": r.name,
                "status": r.status,
                "total_count": r.total_count,
                "valid_count": r.valid_count,
                "invalid_count": r.invalid_count,
                "created_at": r.created_at.isoformat(),
            }
            for r in items
        ],
    }


@router.post("/lists/upload")
async def lists_upload(
    user: User = Depends(get_current_user),
    name: str | None = None,
    file: UploadFile = File(...),
):
    """Upload recipients list (CSV/XLSX); creates list and enqueues processing job."""
    log.info("lists_upload", user_id=str(user.id), filename=file.filename)
    if not file.filename:
        raise BadRequestError("Missing filename")
    content = await file.read()
    rlist = await recipients_service.upload_list(user, name or file.filename, content, file.filename)
    log.info("lists_upload_ok", user_id=str(user.id), list_id=str(rlist.id))
    try:
        await enqueue_process_recipient_list(str(rlist.id))
    except Exception:  # noqa: BLE001; pylint: disable=broad-exception-caught
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
    log.info("list_get", user_id=str(user.id), list_id=list_id)
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
    log.info("list_items", user_id=str(user.id), list_id=list_id, limit=limit, offset=offset)
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
