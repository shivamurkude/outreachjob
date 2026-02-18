"""ARQ job definitions."""

import uuid
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.recipients import process_recipient_list_upload as _process_list

log = get_logger(__name__)


async def _run_with_dlq(
    job_name: str,
    job_id: str | None,
    args: list[Any],
    kwargs: dict[str, Any],
    coro,
) -> None:
    """Run coroutine; on exception persist to FailedJob then re-raise."""
    try:
        await coro
    except Exception as e:
        from app.db.init import init_db
        from app.models.failed_job import FailedJob
        await init_db()
        fid = job_id or str(uuid.uuid4())
        await FailedJob(
            job_name=job_name,
            job_id=fid,
            args=args,
            kwargs=kwargs,
            reason=str(e)[:2000],
            retries=0,
        ).insert()
        log.exception("job_failed", job=job_name, job_id=fid, reason=str(e))
        raise


async def process_recipient_list_upload(ctx: dict[str, Any], list_id: str) -> None:
    """Process uploaded recipient list file (CSV/XLSX) and create recipient_items."""
    job_id = ctx.get("job_id") if isinstance(ctx.get("job_id"), str) else None

    async def _run() -> None:
        log.info("job_start", job="process_recipient_list_upload", list_id=list_id)
        await _process_list(list_id)
        log.info("job_done", job="process_recipient_list_upload", list_id=list_id)

    await _run_with_dlq("process_recipient_list_upload", job_id, [list_id], {}, _run())


async def startup(ctx: dict) -> None:
    from app.db.init import init_db
    await init_db()


async def shutdown(ctx: dict) -> None:
    pass


def get_redis_settings() -> RedisSettings:
    from urllib.parse import urlparse
    s = get_settings()
    u = urlparse(s.redis_url)
    return RedisSettings(
        host=u.hostname or "localhost",
        port=u.port or 6379,
        password=u.password,
        database=int(u.path.lstrip("/")) if u.path else 0,
    )


async def enqueue_process_recipient_list(list_id: str) -> None:
    """Enqueue process_recipient_list_upload job (call from API)."""
    settings = get_redis_settings()
    redis = await create_pool(settings)
    await redis.enqueue_job("process_recipient_list_upload", list_id)
    await redis.close()


# Cron: send_due_emails (Phase 10)
async def send_due_emails(ctx: dict[str, Any]) -> None:
    """Cron job: send scheduled emails that are due (Gmail API)."""
    job_id = ctx.get("job_id") if isinstance(ctx.get("job_id"), str) else None
    from app.worker.cron import run_send_due_emails
    await _run_with_dlq("send_due_emails", job_id, [], {}, run_send_due_emails())
