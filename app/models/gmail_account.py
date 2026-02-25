from datetime import datetime
from typing import List, Literal

from beanie import Document, Link
from pydantic import Field

from app.models.user import User


class GmailAccount(Document):
    user: Link[User]
    email: str  # Gmail address
    # OAuth (auth_type="oauth")
    access_token_encrypted: str = ""
    refresh_token_encrypted: str = ""
    token_expiry: datetime | None = None
    scopes: List[str] = Field(default_factory=list)
    # App password (auth_type="app_password")
    app_password_encrypted: str = ""
    auth_type: Literal["oauth", "app_password"] = "oauth"
    revoked: bool = False
    revoked_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "gmail_accounts"
