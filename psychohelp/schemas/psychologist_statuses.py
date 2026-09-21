from pydantic import BaseModel
from uuid import UUID
from psychohelp.models.psychologist_statuses import PsychologistStatusType
from datetime import datetime

class PsychologistStatusCreateRequest(BaseModel):
    status: PsychologistStatusType
    start_date: datetime
    end_date: datetime

class PsychologistStatusResponse(BaseModel):
    id: UUID
    pid: UUID
    status: PsychologistStatusType
    start_date: datetime
    end_date: datetime

    class Config:
        from_attributes = True