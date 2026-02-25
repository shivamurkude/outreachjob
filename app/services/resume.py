"""Resume upload, parsing, and AI analysis."""

import asyncio
from datetime import datetime

from beanie import PydanticObjectId

from app.core.config import get_settings
from app.core.exceptions import BadRequestError
from app.core.logging import get_logger
from app.models.resume_document import ResumeDocument
from app.models.user import User
from app.services import credits as credits_service
from app.services.resume_analyzer import analyze_resume_with_openai
from app.services.resume_parser import parse_resume
from app.storage.base import get_storage

log = get_logger(__name__)


async def count_resume_scans_this_month(user_id: PydanticObjectId) -> int:
    log.debug("count_resume_scans_this_month", user_id=str(user_id))
    now = datetime.utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    count = await ResumeDocument.find(
        ResumeDocument.user.id == user_id,
        ResumeDocument.created_at >= start,
        ResumeDocument.ai_analysis != None,  # noqa: E711 (Beanie query expr)
    ).count()
    log.debug("count_resume_scans_this_month_ok", user_id=str(user_id), count=count)
    return count


async def upload_resume(user: User, file_content: bytes, filename: str) -> ResumeDocument:
    """Store file in storage, parse, create ResumeDocument."""
    log.info("upload_resume", user_id=str(user.id), filename=filename, size_bytes=len(file_content))
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
    log.info("upload_resume_ok", user_id=str(user.id), doc_id=str(doc.id))
    return doc


async def analyze_resume(user: User, resume_id: PydanticObjectId | None = None) -> ResumeDocument:
    """
    Run AI analysis on resume (latest or by id). Enforce free quota then charge credits.
    """
    log.info("analyze_resume", user_id=str(user.id), resume_id=str(resume_id) if resume_id else None)
    if resume_id:
        doc = await ResumeDocument.find_one(
            ResumeDocument.id == resume_id,
            ResumeDocument.user.id == user.id,
        )
    else:
        doc = await ResumeDocument.find_one(
            ResumeDocument.user.id == user.id,
            sort=[("created_at", -1)],
        )
    if not doc:
        log.warning("analyze_resume_not_found", user_id=str(user.id), resume_id=str(resume_id) if resume_id else None)
        raise BadRequestError("Resume not found")
    if doc.ai_analysis:
        log.info("analyze_resume_ok_already", user_id=str(user.id), doc_id=str(doc.id))
        return doc  # already analyzed

    free_per_month = get_settings().free_resume_scans_per_month
    used = await count_resume_scans_this_month(user.id)
    if used >= free_per_month:
        log.info("analyze_resume_charging_credits", user_id=str(user.id), doc_id=str(doc.id))
        await credits_service.apply_ledger_entry(
            user.id,
            -get_settings().credits_per_resume_scan,
            "resume_scan",
            reference_type="resume_document",
            reference_id=str(doc.id),
        )

    raw = doc.extracted_fields.get("raw_text", "") or ""
    settings = get_settings()
    if settings.openai_api_key and settings.openai_api_key.strip():
        try:
            loop = asyncio.get_event_loop()
            doc.ai_analysis = await loop.run_in_executor(None, lambda: analyze_resume_with_openai(raw))
        except Exception as e:
            log.warning("analyze_resume_openai_fallback", reason=str(e)[:200])
            doc.ai_analysis = {
                "summary": raw[:500] if raw else "",
                "skills": [],
                "experience_years": None,
                "education": [],
                "job_titles": [],
            }
    else:
        log.info("analyze_resume_no_openai_key_placeholder")
        doc.ai_analysis = {
            "summary": raw[:500] if raw else "",
            "skills": [],
            "experience_years": None,
            "education": [],
            "job_titles": [],
        }
    await doc.save()
    log.info("analyze_resume_ok", user_id=str(user.id), doc_id=str(doc.id))
    return doc


async def get_latest_resume(user_id: PydanticObjectId) -> ResumeDocument | None:
    log.debug("get_latest_resume", user_id=str(user_id))
    doc = await ResumeDocument.find_one(
        ResumeDocument.user.id == user_id,
        sort=[("created_at", -1)],
    )
    log.debug("get_latest_resume_ok", user_id=str(user_id), found=doc is not None)
    return doc
