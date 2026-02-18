from datetime import datetime

from beanie import Document, Link
from pydantic import Field

from app.models.user import User


class PaymentOrder(Document):
    """Razorpay order_id -> user_id for webhook attribution."""
    order_id: str
    user: Link[User]
    amount_paise: int
    currency: str = "INR"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "payment_orders"
        indexes = [[("order_id", 1)]]
