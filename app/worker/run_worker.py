"""Run ARQ worker. Usage: python -m app.worker.run_worker"""

import asyncio
from arq import run_worker
from arq.cron import cron
from app.worker.tasks import get_redis_settings, process_recipient_list_upload, send_due_emails, startup, shutdown


async def main():
    await run_worker(
        get_redis_settings(),
        worker_name="findmyjob_worker",
        functions=[process_recipient_list_upload],
        cron_jobs=[
            cron(send_due_emails, second=0),  # every minute at :00
        ],
        on_startup=startup,
        on_shutdown=shutdown,
    )


if __name__ == "__main__":
    asyncio.run(main())
