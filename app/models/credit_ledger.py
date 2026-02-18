from datetime import datetime

from beanie import Document, Link
from pydantic import Field

from app.models.user import User


class CreditLedgerEntry(Document):
    user: Link[User]
    amount: int  # positive = credit, negative = debit
    balance_after: int
    reason: str  # onboarding_bonus, purchase, schedule, verify, resume_scan, refund, referral
    reference_type: str | None = None  # campaign_id, payment_id, etc.
    reference_id: str | None = None
    idempotency_key: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "credit_ledger"
        indexes = [
            [("user", 1), ("created_at", -1)],
            [("idempotency_key", 1)],  # unique in practice per user+reason
        ]
