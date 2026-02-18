from datetime import datetime
from typing import Any, Literal, Optional

from beanie import Document, Link
from pydantic import Field

from app.models.user import User
from app.models.recipient_item import RecipientItem


class EmailVerificationResult(Document):
    user: Link[User]
    recipient_item: Link[RecipientItem] | None = None
    email: str
    result: Literal["valid", "invalid", "unknown", "disposable"] = "unknown"
    mx_valid: bool = False
    syntax_valid: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "email_verification_results"
