from datetime import datetime
from typing import Optional

from beanie import Document, Indexed, Link
from pydantic import Field


class User(Document):
    google_sub: Indexed(str, unique=True)
    email: str
    name: str = ""
    picture: str | None = None
    role: str = "user"  # "user" | "admin"
    referral_code: Indexed(str, unique=True) | None = None
    referred_by: Optional[Link["User"]] = None
    session_version: int = 0
    last_login_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"
