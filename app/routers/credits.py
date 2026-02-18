from fastapi import APIRouter, Depends, Query

from app.deps import get_current_user
from app.models.credit_ledger import CreditLedgerEntry
from app.models.user import User
from app.services import credits as credits_service

router = APIRouter()


@router.get("/balance")
async def credits_balance(user: User = Depends(get_current_user)):
    """Return current credit balance."""
    balance = await credits_service.get_balance(user.id)
    return {"balance": balance}


@router.get("/ledger")
async def credits_ledger(
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Return ledger entries for current user (newest first)."""
    entries = (
        await CreditLedgerEntry.find(CreditLedgerEntry.user.id == user.id)
        .sort(-CreditLedgerEntry.created_at)
        .skip(offset)
        .limit(limit)
        .to_list()
    )
    out = [
        {
            "id": str(e.id),
            "amount": e.amount,
            "balance_after": e.balance_after,
            "reason": e.reason,
            "reference_type": e.reference_type,
            "reference_id": e.reference_id,
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]
    return {"entries": out, "limit": limit, "offset": offset}
