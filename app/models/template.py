from datetime import datetime

from beanie import Document, Link
from pydantic import Field

from app.models.user import User


class Template(Document):
    user: Link[User]
    name: str
    subject: str
    body_html: str
    body_text: str = ""
    unsubscribe_footer: str = ""  # compliance: injected per template
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "templates"
