from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel

from app.core.exceptions import BadRequestError
from app.deps import get_current_user
from app.models.user import User
from app.services import payments as payments_service

router = APIRouter()


class CreateOrderRequest(BaseModel):
    amount_paise: int  # e.g. 25000 for ₹250
    currency: str = "INR"


@router.post("/orders")
async def create_order(
    body: CreateOrderRequest,
  user: User = Depends(get_current_user),
):
    """Create Razorpay order; frontend uses order_id for checkout. Pass user_id in notes when capturing."""
    return await payments_service.create_order(user.id, body.amount_paise, body.currency)


@router.post("/webhook")
async def razorpay_webhook(request: Request, x_razorpay_signature: str = Header(..., alias="X-Razorpay-Signature")):
    """Razorpay webhook: payment.captured -> apply credits (idempotent)."""
    body = await request.body()
    await payments_service.handle_webhook(body, x_razorpay_signature)
    return {"status": "ok"}
