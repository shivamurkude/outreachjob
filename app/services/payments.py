"""Razorpay orders and webhook: idempotent credit apply, offer rules."""

from beanie import PydanticObjectId

from app.core.config import get_settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.security import verify_razorpay_webhook
from app.models.credit_ledger import CreditLedgerEntry
from app.models.user import User
from app.services import credits as credits_service

# Offer: ₹250 pack -> credits (e.g. 100 credits)
PACK_250_CREDITS = 100
FIRST_PURCHASE_BONUS_CREDITS = 20


async def create_order(user_id: PydanticObjectId, amount_paise: int, currency: str = "INR") -> dict:
    """Create Razorpay order; return order_id and amount for frontend."""
    import razorpay
    settings = get_settings()
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise BadRequestError("Payments not configured")
    user = await User.get(user_id)
    if not user:
        raise NotFoundError("User not found")
    client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
    order = client.order.create({"amount": amount_paise, "currency": currency})
    from app.models.payment_order import PaymentOrder
    await PaymentOrder(order_id=order["id"], user=user, amount_paise=amount_paise, currency=currency).insert()
    return {
        "order_id": order["id"],
        "amount": order["amount"],
        "currency": order["currency"],
        "key_id": settings.razorpay_key_id,
    }


async def handle_webhook(payload: bytes, signature: str) -> None:
    """Verify HMAC and apply credits idempotently (payment.captured)."""
    settings = get_settings()
    if not settings.razorpay_webhook_secret:
        raise BadRequestError("Webhook secret not configured")
    if not verify_razorpay_webhook(payload, signature, settings.razorpay_webhook_secret):
        raise BadRequestError("Invalid webhook signature")
    import json
    data = json.loads(payload.decode())
    event = data.get("event")
    if event != "payment.captured":
        return
    payment = data.get("payload", {}).get("payment", {}).get("entity", {})
    order_id = payment.get("order_id")
    payment_id = payment.get("id")
    amount = payment.get("amount")  # paise
    from app.models.payment_order import PaymentOrder
    po = await PaymentOrder.find_one(PaymentOrder.order_id == order_id)
    if not po:
        return
    user_id = po.user.ref
    idempotency_key = f"razorpay_{payment_id}"
    existing = await CreditLedgerEntry.find_one(
        CreditLedgerEntry.user.id == user_id,
        CreditLedgerEntry.idempotency_key == idempotency_key,
    )
    if existing:
        return  # already applied
    # Map amount to credits (e.g. ₹250 = 100 credits)
    if amount == 25000:  # 250 INR
        credits = PACK_250_CREDITS
    else:
        credits = amount // 250  # 1 credit per ₹2.5 approx, or define mapping
    # First purchase bonus
    count = await CreditLedgerEntry.find(
        CreditLedgerEntry.user.id == user_id,
        CreditLedgerEntry.reason == "purchase",
    ).count()
    if count == 0:
        credits += FIRST_PURCHASE_BONUS_CREDITS
    await credits_service.apply_ledger_entry(
        user_id,
        credits,
        "purchase",
        reference_type="razorpay_payment",
        reference_id=payment_id,
        idempotency_key=idempotency_key,
    )
    from app.core.audit import log_event
    await log_event(str(user_id), "payment_captured", "payment", payment_id, {"amount": amount, "credits": credits})
    from app.services.referrals import grant_referral_reward_if_eligible
    await grant_referral_reward_if_eligible(user_id)
