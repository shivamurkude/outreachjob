from datetime import datetime
from typing import Literal

from beanie import Document, Link
from pydantic import Field

from app.models.template import Template
from app.models.user import User


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
    # Background scheduling: "idle" | "in_progress" | "completed"
    scheduling_status: Literal["idle", "in_progress", "completed"] = "idle"
    scheduling_total: int = 0  # total recipients to schedule (set when job starts)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "campaigns"
