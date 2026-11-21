from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from psychohelp.schemas.appointments import AppointmentBase
from psychohelp.schemas.users import UserResponse


class MedicalAppointment(AppointmentBase):
    """Приём в медкарте, включая внутренний комментарий психологам."""

    psychologist_comment: str | None = None


class MedicalRecordPreview(BaseModel):
    id: UUID
    user: UserResponse
    note: str | None


class MedicalRecordResponse(MedicalRecordPreview):
    note_version: int = Field(ge=0)
    next_appointment: MedicalAppointment | None
    completed_appointments: list[MedicalAppointment]
    tests_count: int = Field(ge=0)
    surveys_count: int = Field(ge=0)


class MedicalRecordNoteUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(..., strict=True)
    note_version: int = Field(..., ge=0, strict=True)


class MedicalRecordNoteResponse(BaseModel):
    note: str | None
    note_version: int = Field(ge=0)

    class Config:
        from_attributes = True
