from datetime import datetime
from typing import Literal

from beanie import Document, Link
from pydantic import Field

from app.models.recipient_list import RecipientList


class RecipientItem(Document):
    list: Link[RecipientList]
    email: str
    domain: str = ""
    name: str | None = None
    company: str | None = None
    raw_row: dict = Field(default_factory=dict)
    verification_status: Literal["pending", "valid", "invalid", "unknown"] = "pending"
    chosen_email: str | None = None  # after enrichment
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "recipient_items"
        indexes = [
            [("list", 1), ("email", 1)],
        ]
