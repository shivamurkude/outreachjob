from datetime import datetime
from typing import Literal

from beanie import Document, Link
from pydantic import Field

from app.models.user import User


class RecipientList(Document):
    user: Link[User]
    name: str
    storage_path: str
    status: Literal["processing", "ready", "failed"] = "processing"
    total_count: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "recipient_lists"
