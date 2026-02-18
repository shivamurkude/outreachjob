"""Unit tests for credits service (with in-memory or test DB)."""

import pytest

# Skip if no MongoDB
pytestmark = pytest.mark.asyncio


async def test_get_balance_empty():
    from app.db.init import init_db
    from app.models.user import User
    from app.services import credits as credits_service
    await init_db()
    # Create a user
    user = User(google_sub="test-sub-123", email="test@example.com", name="Test")
    await user.insert()
    balance = await credits_service.get_balance(user.id)
    assert balance == 0


async def test_apply_ledger_entry():
    from app.db.init import init_db
    from app.models.user import User
    from app.services import credits as credits_service
    await init_db()
    user = User(google_sub="test-sub-456", email="test2@example.com", name="Test2")
    await user.insert()
    entry, balance_after = await credits_service.apply_ledger_entry(
        user.id, 100, "onboarding_bonus", idempotency_key="test-key-1"
    )
    assert entry.amount == 100
    assert balance_after == 100
    # Idempotency: same key should not double-apply
    entry2, balance2 = await credits_service.apply_ledger_entry(
        user.id, 100, "onboarding_bonus", idempotency_key="test-key-1"
    )
    assert balance2 == 100
    assert entry.id == entry2.id
