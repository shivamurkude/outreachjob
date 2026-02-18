"""Audit log for critical actions."""

from typing import Any

from app.models.audit_log import AuditLog


async def log_event(
    user_id: str | None,
    event_type: str,
    entity_type: str,
    entity_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append to audit_logs collection."""
    await AuditLog(
        user_id=user_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata=metadata or {},
    ).insert()
