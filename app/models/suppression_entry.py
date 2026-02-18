"""Suppression list: global and per-user emails to exclude from sending."""

from datetime import datetime

from beanie import Document
from pydantic import Field


class SuppressionEntry(Document):
    email: str
    user_id: str | None = None  # None = global
    source: str = "verification"  # verification | manual
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "suppression_entries"
        indexes = [
            [("email", 1), ("user_id", 1)],  # unique in practice: one (email, user_id)
            [("user_id", 1)],
        ]
