from datetime import datetime

from beanie import Document
from pydantic import Field


class SystemRecipient(Document):
    email: str
    domain: str = ""
    name: str | None = None
    company: str | None = None
    source: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "system_recipients"
        indexes = [
            [("email", 1)],
            [("domain", 1)],
        ]
