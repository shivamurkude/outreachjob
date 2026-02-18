from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from app.deps import get_current_user
from app.models.user import User
from app.services import verification as verification_service

router = APIRouter()


class VerifyEmailRequest(BaseModel):
    email: str
    recipient_item_id: str | None = None


class VerifyBulkRequest(BaseModel):
    emails: list[str]
    idempotency_key: str | None = None


@router.post("/email")
async def verify_email(
    body: VerifyEmailRequest,
    user: User = Depends(get_current_user),
):
    """Verify single email (syntax, MX, disposable). Charges 1 credit."""
    from beanie import PydanticObjectId
    rid = PydanticObjectId(body.recipient_item_id) if body.recipient_item_id else None
    evr = await verification_service.verify_email_for_user(
        user.id, body.email.strip(), recipient_item_id=rid
    )
    return {
        "email": evr.email,
        "result": evr.result,
        "syntax_valid": evr.syntax_valid,
        "mx_valid": evr.mx_valid,
    }


@router.post("/bulk")
async def verify_bulk(
    body: VerifyBulkRequest,
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    """Verify multiple emails; charge upfront. Optional Idempotency-Key header."""
    key = idempotency_key or body.idempotency_key
    results = await verification_service.verify_bulk(user.id, body.emails, idempotency_key=key)
    return {
        "results": [
            {"email": r.email, "result": r.result, "syntax_valid": r.syntax_valid, "mx_valid": r.mx_valid}
            for r in results
        ]
    }
