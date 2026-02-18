from fastapi import APIRouter, Depends, File, UploadFile

from app.core.exceptions import BadRequestError
from app.deps import get_current_user
from app.models.user import User
from app.services import resume as resume_service

router = APIRouter()


@router.post("/upload")
async def resume_upload(
    user: User = Depends(get_current_user),
    file: UploadFile = File(...),
):
    """Upload resume (PDF/DOCX); stored and parsed."""
    if not file.filename:
        raise BadRequestError("Missing filename")
    content = await file.read()
    doc = await resume_service.upload_resume(user, content, file.filename)
    return {
        "id": str(doc.id),
        "filename": doc.filename,
        "extracted_fields": doc.extracted_fields,
        "created_at": doc.created_at.isoformat(),
    }


@router.post("/analyze")
async def resume_analyze(
    user: User = Depends(get_current_user),
    resume_id: str | None = None,
):
    """Run AI analysis on latest or specified resume. Uses free quota then charges credits."""
    from beanie import PydanticObjectId
    rid = PydanticObjectId(resume_id) if resume_id else None
    doc = await resume_service.analyze_resume(user, rid)
    return {
        "id": str(doc.id),
        "filename": doc.filename,
        "extracted_fields": doc.extracted_fields,
        "ai_analysis": doc.ai_analysis,
        "created_at": doc.created_at.isoformat(),
    }


@router.get("/latest")
async def resume_latest(user: User = Depends(get_current_user)):
    """Return latest resume document for current user."""
    doc = await resume_service.get_latest_resume(user.id)
    if not doc:
        return {"resume": None}
    return {
        "resume": {
            "id": str(doc.id),
            "filename": doc.filename,
            "extracted_fields": doc.extracted_fields,
            "ai_analysis": doc.ai_analysis,
            "created_at": doc.created_at.isoformat(),
        }
    }
