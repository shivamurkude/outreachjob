from datetime import datetime
from typing import Any

from beanie import Document
from pydantic import Field


class AuditLog(Document):
    user_id: str | None = None  # optional for system events
    event_type: str
    entity_type: str
    entity_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "audit_logs"
        indexes = [
            [("user_id", 1), ("created_at", -1)],
            [("entity_type", 1), ("entity_id", 1)],
        ]
