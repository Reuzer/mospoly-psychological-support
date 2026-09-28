from uuid import UUID

from pydantic import BaseModel
from typing import Optional


class PsychologistBase(BaseModel):
    id: UUID
    experience: str
    qualification: str
    consult_areas: str
    description: str
    office: str
    education: str
    short_description: str
    photo: str | None

    class Config:
        from_attributes = True


class PsychologistCreateRequest(BaseModel):
    user_id: UUID
    experience: str
    qualification: str
    consult_areas: str
    description: str
    office: str
    education: str
    short_description: str
    photo: str | None = None


class PsychologistResponse(BaseModel):
    id: UUID
    experience: str
    qualification: str
    consult_areas: str
    description: str
    office: str
    education: str
    short_description: str
    photo: str | None
    first_name: str
    middle_name: str | None
    last_name: str
    phone_number: str

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_psychologist(cls, psychologist):
        return cls(
            id=psychologist.id,
            experience=psychologist.experience,
            qualification=psychologist.qualification,
            consult_areas=psychologist.consult_areas,
            description=psychologist.description,
            office=psychologist.office,
            education=psychologist.education,
            short_description=psychologist.short_description,
            photo=psychologist.photo,
            first_name=psychologist.user.first_name,
            middle_name=psychologist.user.middle_name,
            last_name=psychologist.user.last_name,
            phone_number=psychologist.user.phone_number,
        )


class ScheduleSlot(BaseModel):
    datetime: str
    duration: int
    format: str
    address: Optional[str] = None
    price: int

class PsychologistScheduleResponse(BaseModel):
    available_slots: list[ScheduleSlot]

