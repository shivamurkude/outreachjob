from fastapi import APIRouter, Depends, File, UploadFile

from app.core.exceptions import BadRequestError
from app.deps import require_admin
from app.models.user import User
from app.services import admin_recipients as admin_recipients_service
from app.services.recipients import parse_csv, parse_xlsx

router = APIRouter()


@router.post("/recipients/import")
async def admin_recipients_import(
    user: User = Depends(require_admin),
    file: UploadFile = File(...),
    source: str = "import",
):
    """Admin: import system recipients from CSV (email, name, company, domain)."""
    if not file.filename:
        raise BadRequestError("Missing filename")
    content = await file.read()
    if file.filename.lower().endswith(".xlsx"):
        rows = parse_xlsx(content)
    else:
        rows = parse_csv(content)
    out = await admin_recipients_service.import_system_recipients(rows, source=source, user_id=str(user.id))
    return out


@router.post("/recipients/refresh")
async def admin_recipients_refresh(user: User = Depends(require_admin)):
    """Admin: trigger daily refresh of system recipients."""
    out = await admin_recipients_service.refresh_system_recipients()
    return out
