"""Run ARQ worker. Usage: python -m app.worker.run_worker"""

import asyncio

# Allow nested event loops so the worker runs under debugpy (VS Code/Cursor debugger)
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

from arq import run_worker
from arq.cron import cron

from app.worker.tasks import (
    get_redis_settings,
    process_recipient_list_upload,
    schedule_campaign_background,
    send_due_emails,
    shutdown,
    startup,
)


async def main():
    await run_worker(
        get_redis_settings(),
        functions=[process_recipient_list_upload, schedule_campaign_background],
        cron_jobs=[
            cron(send_due_emails, second=0),  # every minute at :00
        ],
        on_startup=startup,
        on_shutdown=shutdown,
    )


if __name__ == "__main__":
    asyncio.run(main())
