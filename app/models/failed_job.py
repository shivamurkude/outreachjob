"""Dead-letter: failed ARQ jobs for inspection."""

from datetime import datetime
from typing import Any

from beanie import Document
from pydantic import Field


class FailedJob(Document):
    job_name: str
    job_id: str
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    retries: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "failed_jobs"
        indexes = [[("job_name", 1)], [("created_at", -1)]]
