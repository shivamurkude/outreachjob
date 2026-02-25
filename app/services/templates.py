"""Templates CRUD and AI generator with compliance footer."""

from beanie import PydanticObjectId

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.template import Template
from app.models.user import User

log = get_logger(__name__)
DEFAULT_UNSUBSCRIBE_FOOTER = (
    "\n\n---\nYou received this email because you were contacted for a job opportunity. "
    "To unsubscribe, reply with UNSUBSCRIBE in the subject."
)


async def create_template(
    user_id: PydanticObjectId,
    name: str,
    subject: str,
    body_html: str,
    body_text: str = "",
    unsubscribe_footer: str | None = None,
) -> Template:
    log.info("create_template", user_id=str(user_id), name=name)
    user = await User.get(user_id)
    if not user:
        raise NotFoundError("User not found")
    footer = unsubscribe_footer if unsubscribe_footer is not None else DEFAULT_UNSUBSCRIBE_FOOTER
    t = Template(
        user=user,
        name=name,
        subject=subject,
        body_html=body_html,
        body_text=body_text or "",
        unsubscribe_footer=footer,
    )
    await t.insert()
    log.info("create_template_ok", user_id=str(user_id), template_id=str(t.id))
    return t


async def get_template(template_id: PydanticObjectId, user_id: PydanticObjectId) -> Template | None:
    log.debug("get_template", template_id=str(template_id), user_id=str(user_id))
    t = await Template.find_one(
        Template.id == template_id,
        Template.user.id == user_id,
    )
    log.debug("get_template_ok", template_id=str(template_id), found=t is not None)
    return t


async def list_templates(user_id: PydanticObjectId) -> list[Template]:
    log.debug("list_templates", user_id=str(user_id))
    items = await Template.find(Template.user.id == user_id).to_list()
    log.debug("list_templates_ok", user_id=str(user_id), count=len(items))
    return items


async def update_template(
    template_id: PydanticObjectId,
    user_id: PydanticObjectId,
    name: str | None = None,
    subject: str | None = None,
    body_html: str | None = None,
    body_text: str | None = None,
    unsubscribe_footer: str | None = None,
) -> Template | None:
    log.info("update_template", template_id=str(template_id), user_id=str(user_id))
    t = await get_template(template_id, user_id)
    if not t:
        log.debug("update_template_not_found", template_id=str(template_id))
        return None
    if name is not None:
        t.name = name
    if subject is not None:
        t.subject = subject
    if body_html is not None:
        t.body_html = body_html
    if body_text is not None:
        t.body_text = body_text
    if unsubscribe_footer is not None:
        t.unsubscribe_footer = unsubscribe_footer
    from datetime import datetime
    t.updated_at = datetime.utcnow()
    await t.save()
    log.info("update_template_ok", template_id=str(template_id))
    return t


async def delete_template(template_id: PydanticObjectId, user_id: PydanticObjectId) -> bool:
    log.info("delete_template", template_id=str(template_id), user_id=str(user_id))
    t = await get_template(template_id, user_id)
    if not t:
        log.debug("delete_template_not_found", template_id=str(template_id))
        return False
    await t.delete()
    log.info("delete_template_ok", template_id=str(template_id))
    return True


def inject_footer(body_html: str, footer: str) -> str:
    """Append unsubscribe footer to body (compliance)."""
    log.debug("inject_footer", has_footer=bool(footer))
    if not footer:
        return body_html
    return body_html.rstrip() + "\n\n" + footer


async def generate_template_from_resume(
    user_id: PydanticObjectId,
    job_title: str,
    resume_profile_summary: str = "",
) -> dict[str, str]:
    """
    Placeholder AI template generator (resume + job title).
    In prod, call OpenAI for structured output.
    """
    log.info("generate_template_from_resume", user_id=str(user_id), job_title=job_title)
    subject = f"Application for {job_title}"
    body = f"Hi,\n\nI am writing to apply for the {job_title} position.\n\n{resume_profile_summary or 'Please find my details in the attached resume.'}\n\nBest regards"
    out = {"subject": subject, "body_text": body, "body_html": body.replace("\n", "<br>\n")}
    log.info("generate_template_from_resume_ok", user_id=str(user_id))
    return out
