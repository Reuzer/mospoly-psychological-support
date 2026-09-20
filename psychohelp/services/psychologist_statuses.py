from datetime import datetime
from uuid import UUID

from psychohelp.models.psychologist_statuses import PsychologistStatusType
from psychohelp.repositories.psychologist_statuses.psychologist_statuses import (
    set_psychologist_status,
    delete_status_by_id,
    get_psychologist_statuses_by_id,
)

async def set_status(psychologist_id: UUID, start_date: datetime, end_date: datetime, status: PsychologistStatusType):
    return await set_psychologist_status(psychologist_id, start_date, end_date, status)

async def delete_status(status_id: UUID):
    return await delete_status_by_id(status_id)

async def get_psychologist_statuses_service(psychologist_id: UUID):
    return await get_psychologist_statuses_by_id(psychologist_id)