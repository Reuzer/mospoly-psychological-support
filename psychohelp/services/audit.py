from uuid import UUID
from datetime import datetime, timezone
from psychohelp.config.config import get_async_db
from psychohelp.models.application_audit_log import ApplicationAuditLog


async def log_application_status_change(
    application_id: UUID,
    previous_status: str | None,
    new_status: str,
    actor_type: str,
    actor_id: UUID | None,
    comment: str | None = None
) -> None:
    async with get_async_db() as session:
        log_entry = ApplicationAuditLog(
            application_id=application_id,
            previous_status=previous_status,
            new_status=new_status,
            actor_type=actor_type,
            actor_id=actor_id,
            comment=comment
        )
        session.add(log_entry)
        await session.commit()