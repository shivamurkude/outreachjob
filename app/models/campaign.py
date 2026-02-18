from datetime import datetime
from typing import Literal, Optional

from beanie import Document, Link
from pydantic import Field

from app.models.user import User
from app.models.template import Template


class Campaign(Document):
    user: Link[User]
    name: str
    template: Link[Template]
    status: Literal["draft", "scheduled", "paused", "completed"] = "draft"
    recipient_source: Literal["list", "system"] = "list"
    recipient_list_id: str | None = None
    scheduled_count: int = 0
    sent_count: int = 0
    failed_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "campaigns"
