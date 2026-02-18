"""Templates CRUD and AI generator with compliance footer."""

from beanie import PydanticObjectId

from app.core.exceptions import NotFoundError
from app.models.template import Template
from app.models.user import User

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
    return t


async def get_template(template_id: PydanticObjectId, user_id: PydanticObjectId) -> Template | None:
    return await Template.find_one(
        Template.id == template_id,
        Template.user.id == user_id,
    )


async def list_templates(user_id: PydanticObjectId) -> list[Template]:
    return await Template.find(Template.user.id == user_id).to_list()


async def update_template(
    template_id: PydanticObjectId,
    user_id: PydanticObjectId,
    name: str | None = None,
    subject: str | None = None,
    body_html: str | None = None,
    body_text: str | None = None,
    unsubscribe_footer: str | None = None,
) -> Template | None:
    t = await get_template(template_id, user_id)
    if not t:
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
    return t


async def delete_template(template_id: PydanticObjectId, user_id: PydanticObjectId) -> bool:
    t = await get_template(template_id, user_id)
    if not t:
        return False
    await t.delete()
    return True


def inject_footer(body_html: str, footer: str) -> str:
    """Append unsubscribe footer to body (compliance)."""
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
    subject = f"Application for {job_title}"
    body = f"Hi,\n\nI am writing to apply for the {job_title} position.\n\n{resume_profile_summary or 'Please find my details in the attached resume.'}\n\nBest regards"
    return {"subject": subject, "body_text": body, "body_html": body.replace("\n", "<br>\n")}
