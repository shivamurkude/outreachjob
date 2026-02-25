from fastapi import APIRouter, Depends, Query

from app.core.logging import get_logger
from app.deps import get_current_user
from app.models.credit_ledger import CreditLedgerEntry
from app.models.user import User
from app.services import credits as credits_service

router = APIRouter()
log = get_logger(__name__)


@router.get("/balance")
async def credits_balance(user: User = Depends(get_current_user)):
    """Return current credit balance."""
    log.info("credits_balance", user_id=str(user.id))
    balance = await credits_service.get_balance(user.id)
    log.info("credits_balance_ok", user_id=str(user.id), balance=balance)
    return {"balance": balance}


@router.get("/ledger")
async def credits_ledger(
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Return ledger entries for current user (newest first)."""
    log.info("credits_ledger", user_id=str(user.id), limit=limit, offset=offset)
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
    log.info("credits_ledger_ok", user_id=str(user.id), count=len(out))
    return {"entries": out, "limit": limit, "offset": offset}
