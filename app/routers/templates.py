from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.exceptions import BadRequestError
from app.deps import get_current_user
from app.models.user import User
from app.services import templates as templates_service

router = APIRouter()


class TemplateCreate(BaseModel):
    name: str
    subject: str
    body_html: str
    body_text: str = ""
    unsubscribe_footer: str | None = None


class TemplateUpdate(BaseModel):
    name: str | None = None
    subject: str | None = None
    body_html: str | None = None
    body_text: str | None = None
    unsubscribe_footer: str | None = None


class GenerateTemplateRequest(BaseModel):
    job_title: str
    resume_profile_summary: str = ""


@router.get("")
async def templates_list(user: User = Depends(get_current_user)):
    """List templates for current user."""
    items = await templates_service.list_templates(user.id)
    return {
        "templates": [
            {"id": str(t.id), "name": t.name, "subject": t.subject, "updated_at": t.updated_at.isoformat()}
            for t in items
        ]
    }


@router.post("")
async def template_create(
    body: TemplateCreate,
    user: User = Depends(get_current_user),
):
    """Create template with optional unsubscribe footer."""
    t = await templates_service.create_template(
        user.id,
        body.name,
        body.subject,
        body.body_html,
        body_text=body.body_text,
        unsubscribe_footer=body.unsubscribe_footer,
    )
    return {"id": str(t.id), "name": t.name, "subject": t.subject, "created_at": t.created_at.isoformat()}


@router.get("/{template_id}")
async def template_get(template_id: str, user: User = Depends(get_current_user)):
    from beanie import PydanticObjectId
    t = await templates_service.get_template(PydanticObjectId(template_id), user.id)
    if not t:
        raise BadRequestError("Template not found")
    return {
        "id": str(t.id),
        "name": t.name,
        "subject": t.subject,
        "body_html": t.body_html,
        "body_text": t.body_text,
        "unsubscribe_footer": t.unsubscribe_footer,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
    }


@router.put("/{template_id}")
async def template_update(
    template_id: str,
    body: TemplateUpdate,
    user: User = Depends(get_current_user),
):
    from beanie import PydanticObjectId
    t = await templates_service.update_template(
        PydanticObjectId(template_id),
        user.id,
        name=body.name,
        subject=body.subject,
        body_html=body.body_html,
        body_text=body.body_text,
        unsubscribe_footer=body.unsubscribe_footer,
    )
    if not t:
        raise BadRequestError("Template not found")
    return {"id": str(t.id), "name": t.name, "updated_at": t.updated_at.isoformat()}


@router.delete("/{template_id}")
async def template_delete(template_id: str, user: User = Depends(get_current_user)):
    from beanie import PydanticObjectId
    ok = await templates_service.delete_template(PydanticObjectId(template_id), user.id)
    if not ok:
        raise BadRequestError("Template not found")
    return {"status": "deleted"}


@router.post("/generate")
async def template_generate(
  body: GenerateTemplateRequest,
  user: User = Depends(get_current_user),
):
    """Generate template draft from job title and optional resume summary (AI placeholder)."""
    out = await templates_service.generate_template_from_resume(
        user.id,
        body.job_title,
        body.resume_profile_summary,
    )
    return out
