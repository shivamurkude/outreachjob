from datetime import datetime

from beanie import Document, Link
from pydantic import Field

from app.models.recipient_item import RecipientItem
from app.models.user import User


class EnrichmentResult(Document):
    user: Link[User]
    recipient_item: Link[RecipientItem]
    chosen_email: str
    role: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "enrichment_results"
