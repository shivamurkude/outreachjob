"""Resume upload, parsing, and AI analysis."""

from datetime import datetime

from beanie import PydanticObjectId

from app.core.config import get_settings
from app.core.exceptions import BadRequestError
from app.models.resume_document import ResumeDocument
from app.models.user import User
from app.services import credits as credits_service
from app.services.resume_parser import parse_resume
from app.storage.base import get_storage


async def count_resume_scans_this_month(user_id: PydanticObjectId) -> int:
    now = datetime.utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    count = await ResumeDocument.find(
        ResumeDocument.user.id == user_id,
        ResumeDocument.created_at >= start,
        ResumeDocument.ai_analysis != None,  # noqa: E711 (Beanie query expr)
    ).count()
    return count


async def upload_resume(user: User, file_content: bytes, filename: str) -> ResumeDocument:
    """Store file in storage, parse, create ResumeDocument."""
    storage = get_storage()
    key = f"resumes/{user.id}/{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{filename}"
    await storage.put(key, file_content, content_type="application/octet-stream")
    extracted = parse_resume(file_content, filename)
    doc = ResumeDocument(
        user=user,
        storage_path=key,
        filename=filename,
        extracted_fields=extracted,
    )
    await doc.insert()
    return doc


async def analyze_resume(user: User, resume_id: PydanticObjectId | None = None) -> ResumeDocument:
    """
    Run AI analysis on resume (latest or by id). Enforce free quota then charge credits.
    """
    if resume_id:
        doc = await ResumeDocument.find_one(
            ResumeDocument.id == resume_id,
            ResumeDocument.user.id == user.id,
        )
    else:
        doc = await ResumeDocument.find_one(
            ResumeDocument.user.id == user.id,
            sort=-ResumeDocument.created_at,
        )
    if not doc:
        raise BadRequestError("Resume not found")
    if doc.ai_analysis:
        return doc  # already analyzed

    free_per_month = get_settings().free_resume_scans_per_month
    used = await count_resume_scans_this_month(user.id)
    if used >= free_per_month:
        # Charge credits
        await credits_service.apply_ledger_entry(
            user.id,
            -get_settings().credits_per_resume_scan,
            "resume_scan",
            reference_type="resume_document",
            reference_id=str(doc.id),
        )

    # Placeholder AI analysis (structured output); integrate OpenAI in prod
    raw = doc.extracted_fields.get("raw_text", "")[:4000]
    doc.ai_analysis = {
        "summary": raw[:500] if raw else "",
        "skills": [],
        "experience_years": None,
        "education": [],
    }
    await doc.save()
    return doc


async def get_latest_resume(user_id: PydanticObjectId) -> ResumeDocument | None:
    return await ResumeDocument.find_one(
        ResumeDocument.user.id == user_id,
        sort=-ResumeDocument.created_at,
    )
