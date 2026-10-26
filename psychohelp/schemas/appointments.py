from psychohelp.repositories.appointments import (
    AppointmentType,
    AppointmentStatus,
    UUID,
)
from psychohelp.models.appointment_reschedule_requests import AppointmentRescheduleStatus
from pydantic import BaseModel, EmailStr, Field, model_validator
from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, field_validator
from datetime import datetime
from typing import Optional


# --- Полные схемы для вложенных объектов ---

class UserFullResponse(BaseModel):
    id: UUID
    first_name: str
    middle_name: Optional[str] = None
    last_name: str
    phone_number: str
    email: EmailStr
    social_media: Optional[str] = None
    study_group: Optional[str] = None
    # Пароль намеренно исключен

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
    # Вложенный профиль пользователя для психолога
    user: UserFullResponse 

    class Config:
        from_attributes = True


# --- Основные схемы ---

class AppointmentBase(BaseModel):
    id: UUID
    
    # Полные вложенные объекты вместо UUID
    patient: UserFullResponse
    psychologist: PsychologistFullResponse
    
    application_id: Optional[UUID] = None
    type: AppointmentType
    reason: Optional[str] = None
    status: AppointmentStatus
    scheduled_time: datetime
    remind_time: Optional[datetime] = None
    last_change_time: datetime
    venue: str
    comment: Optional[str] = None
    cancel_reason: Optional[str] = None
    patient_comment: Optional[str] = None
    conclusion: Optional[str] = None
    emergency_contact: Optional[str] = None

    class Config:
        from_attributes = True
        use_enum_values = True


class AppointmentCreateRequest(BaseModel):
    application_id: Optional[UUID] = Field(
        None,
        deprecated=True,
        description="Для самостоятельной записи передавать не нужно. "
        "Записи по заявке создаются только через POST /applications/{application_id}/confirm; "
        "непустое значение возвращает 400.",
    )
    patient_id: UUID
    psychologist_id: UUID
    type: AppointmentType
    scheduled_time: datetime
    reason: Optional[str] = None
    remind_time: Optional[datetime] = None
    venue: Optional[str] = None
    comment: Optional[str] = None


class AppointmentEmergencyContactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    emergency_contact: str | None = Field(..., max_length=512, strict=True)

    @field_validator("emergency_contact", mode="before")
    @classmethod
    def normalize_emergency_contact(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


class AppointmentCancelRequest(BaseModel):
    cancel_reason: str


class AppointmentDoneRequest(BaseModel):
    patient_comment: Optional[str] = Field(None, min_length=1, max_length=2048)
    psychologist_comment: Optional[str] = Field(None, max_length=2048)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_conclusion(cls, data):
        if (
            isinstance(data, dict)
            and "patient_comment" not in data
            and "conclusion" in data
        ):
            data = {**data, "patient_comment": data["conclusion"]}
        return data


class AppointmentRescheduleRequestCreate(BaseModel):
    scheduled_time: datetime
    remind_time: Optional[datetime] = None
    venue: Optional[str] = Field(None, min_length=1, max_length=128)
    comment: Optional[str] = Field(None, max_length=512)


class AppointmentRescheduleCancelRequest(BaseModel):
    rejection_comment: str = Field(..., min_length=1, max_length=512)


# Backward-compatible import for integrations using the previous schema name.
AppointmentRescheduleRejectRequest = AppointmentRescheduleCancelRequest


class AppointmentRescheduleRequestResponse(BaseModel):
    id: UUID
    appointment_id: UUID
    requested_by_user_id: Optional[UUID] = None
    status: AppointmentRescheduleStatus
    old_scheduled_time: datetime
    old_remind_time: Optional[datetime] = None
    old_venue: str
    old_comment: Optional[str] = None
    requested_scheduled_time: datetime
    requested_remind_time: Optional[datetime] = None
    requested_venue: Optional[str] = None
    requested_comment: Optional[str] = None
    rejection_comment: Optional[str] = None
    created_at: datetime
    responded_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        use_enum_values = True
