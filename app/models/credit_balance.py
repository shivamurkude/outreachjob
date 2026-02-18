from beanie import Document, Link

from app.models.user import User


class CreditBalance(Document):
    """Current balance per user; updated atomically with ledger."""
    user: Link[User]
    balance: int = 0

    class Settings:
        name = "credit_balances"
        indexes = [[("user", 1)]]
