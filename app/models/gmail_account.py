from datetime import datetime
from typing import List

from beanie import Document, Link
from pydantic import Field

from app.models.user import User


class GmailAccount(Document):
    user: Link[User]
    email: str  # Gmail address
    access_token_encrypted: str = ""
    refresh_token_encrypted: str = ""
    token_expiry: datetime | None = None
    scopes: List[str] = Field(default_factory=list)
    revoked: bool = False
    revoked_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "gmail_accounts"
