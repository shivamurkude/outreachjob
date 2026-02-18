from datetime import datetime
from typing import Any

from beanie import Document, Link
from pydantic import Field

from app.models.user import User


class ResumeDocument(Document):
    user: Link[User]
    storage_path: str
    filename: str
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    ai_analysis: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "resume_documents"
