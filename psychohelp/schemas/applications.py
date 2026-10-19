from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from uuid import UUID
from datetime import datetime
from enum import Enum
from typing import Optional


class UserFullResponse(BaseModel):
    id: UUID
    first_name: str
    middle_name: Optional[str] = None
    last_name: str
    phone_number: str
    email: EmailStr
    social_media: Optional[str] = None
    study_group: Optional[str] = None

    class Config:
        from_attributes = True


class PsychologistFullResponse(BaseModel):
    id: UUID
    user_id: UUID
    experience: str
    qualification: str
    consult_areas: str
    description: str
    office: str
    education: str
    short_description: str
    photo: Optional[str] = None
    user: Optional[UserFullResponse] = None

    class Config:
        from_attributes = True


class AppointmentFullResponse(BaseModel):
    id: UUID
    patient: UserFullResponse
    application_id: Optional[UUID] = None
    psychologist_id: UUID
    type: str
    reason: Optional[str] = None
    status: str
    cancel_reason: Optional[str] = None
    patient_comment: Optional[str] = None
    conclusion: Optional[str] = None
    scheduled_time: datetime
    remind_time: Optional[datetime] = None
    last_change_time: datetime
    venue: str
    comment: Optional[str] = None

    class Config:
        from_attributes = True


class UniversityStatus(str, Enum):
    STUDENT = "студент"
    POSTGRADUATE = "аспирант"
    TEACHER = "преподаватель"
    STAFF = "сотрудник"


class ApplicationStatus(str, Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    AWAITING_USER_CONFIRMATION = "awaiting_user_confirmation"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class CancelInitiator(str, Enum):
    USER = "user"
    PSYCHOLOGIST = "psychologist"
    MANAGER = "manager"
    SYSTEM = "system"


class MeetingType(str, Enum):
    OFFLINE = "offline"
    ONLINE = "online"


class ApplicationCreateRequest(BaseModel):
    psychologist_id: UUID
    scheduled_at: datetime
    problem_description: str = Field(..., min_length=10, max_length=2000)
    preferred_campus: Optional[str] = Field(None, max_length=128)
    university_status: UniversityStatus


class AcceptToProcessingRequest(BaseModel):
    assigned_to: UUID


class OfferConsultationRequest(BaseModel):
    psychologist_id: UUID
    meeting_type: MeetingType
    scheduled_at: datetime
    location_address: Optional[str] = None
    meeting_url: Optional[str] = None

    @field_validator("scheduled_at")
    def validate_scheduled_at(cls, v):
        if v <= datetime.now(v.tzinfo):
            raise ValueError("Дата и время встречи не могут быть в прошлом")
        return v


class ApplicationReassignRequest(BaseModel):
    """Изменяемые условия повторного предложения; психолог определяется по сессии."""

    model_config = ConfigDict(extra="forbid")

    meeting_type: Optional[MeetingType] = None
    scheduled_at: Optional[datetime] = None
    location_address: Optional[str] = Field(None, min_length=1, max_length=128)
    meeting_url: Optional[str] = Field(None, min_length=1, max_length=128)

    @field_validator("meeting_type", "scheduled_at")
    @classmethod
    def reject_explicit_null(cls, value):
        if value is None:
            raise ValueError("Поле не может быть null")
        return value

    @field_validator("location_address", "meeting_url")
    @classmethod
    def trim_location(cls, value):
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("Место встречи не может быть пустым")
        return value


class ApplicationConfirmRequest(BaseModel):
    """Подтверждение пользователем конкретной версии предложения."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(
        ..., ge=1, strict=True,
        description="Значение version из последнего полученного предложения. "
        "Если условия изменились, сервер возвращает 409 без создания записи.",
    )


class RejectRequest(BaseModel):
    reject_reason: str = Field(..., min_length=1, max_length=500)


class CancelRequest(BaseModel):
    cancel_reason: str = Field(..., min_length=1, max_length=500)
    cancel_initiator: CancelInitiator


class ApplicationResponse(BaseModel):
    id: UUID

    user: Optional[UserFullResponse] = None
    assigned_to_user: Optional[UserFullResponse] = None
    psychologist: Optional[PsychologistFullResponse] = None
    appointment: Optional[AppointmentFullResponse] = None

    problem_description: str
    preferred_campus: Optional[str]
    university_status: UniversityStatus
    status: ApplicationStatus

    meeting_type: Optional[MeetingType]
    scheduled_at: Optional[datetime]
    location_address: Optional[str]
    meeting_url: Optional[str]

    created_at: datetime
    updated_at: datetime
    processing_started_at: Optional[datetime]
    confirmation_requested_at: Optional[datetime]
    completed_at: Optional[datetime]
    rejected_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    expired_at: Optional[datetime]

    reject_reason: Optional[str]
    cancel_reason: Optional[str]
    cancel_initiator: Optional[CancelInitiator]
    internal_comment: Optional[str]
    version: int

    class Config:
        from_attributes = True
        use_enum_values = True
