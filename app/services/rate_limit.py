"""Gmail send rate limit: daily cap per account via Redis."""

from datetime import datetime

from app.core.config import get_settings

KEY_PREFIX = "gmail:send_count"
TTL_SECONDS = 25 * 3600  # 25 hours so key expires after the day


def _key(gmail_account_id: str) -> str:
    date = datetime.utcnow().strftime("%Y-%m-%d")
    return f"{KEY_PREFIX}:{gmail_account_id}:{date}"


async def get_gmail_sent_today(redis, gmail_account_id: str) -> int:
    """Return current send count for this Gmail account today."""
    try:
        val = await redis.get(_key(gmail_account_id))
        return int(val) if val is not None else 0
    except Exception:
        return 0


async def incr_gmail_sent_today(redis, gmail_account_id: str) -> int:
    """Increment and return new count; set TTL on first increment."""
    key = _key(gmail_account_id)
    try:
        n = await redis.incr(key)
        if n == 1:
            await redis.expire(key, TTL_SECONDS)
        return n
    except Exception:
        return 0


def gmail_daily_cap() -> int:
    return get_settings().gmail_daily_cap
