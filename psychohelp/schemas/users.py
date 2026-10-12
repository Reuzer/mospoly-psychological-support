from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic_extra_types.phone_numbers import PhoneNumber
from typing import Optional
from psychohelp.schemas.roles import RoleResponse 
from uuid import UUID


PhoneNumber.phone_format = "E164"
PhoneNumber.default_region_code = "+7"


class UserCreateRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=50)
    middle_name: str | None = Field(None, min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    phone_number: PhoneNumber
    email: EmailStr
    social_media: str | None = Field(None, max_length=50)
    password: str = Field(min_length=8, max_length=256)
    study_group: Optional[str] = Field(None, max_length=50)


class UserBase(BaseModel):
    id: UUID
    first_name: str = Field(min_length=1, max_length=50)
    middle_name: str | None = Field(None, min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    phone_number: PhoneNumber
    email: EmailStr
    social_media: str | None = Field(None, max_length=50)
    password: str


class UserResponse(BaseModel):
    id: UUID
    first_name: str = Field(min_length=1, max_length=50)
    middle_name: str | None = Field(None, min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    phone_number: PhoneNumber
    email: EmailStr
    social_media: str | None = Field(None, max_length=50)
    roles: list[RoleResponse] = []
    study_group: Optional[str] = None

    class Config:
        from_attributes = True


class PsychologistPublicCard(BaseModel):
    """Публичная карточка психолога: без контактов и учебных данных"""
    id: UUID
    first_name: str
    middle_name: str | None = None
    last_name: str

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    status_code: int
    access_token: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=64)


class UserUpdateRequest(BaseModel):
    """Схема для обновления профиля (все поля опциональны)"""
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    middle_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    phone_number: Optional[str] = Field(None, min_length=10, max_length=20)
    email: Optional[EmailStr] = None
    social_media: Optional[str] = Field(None, max_length=50)
    study_group: Optional[str] = Field(None, max_length=50)

    # Обязательные поля можно не передавать, но нельзя очистить через null.
    # Остальные (middle_name, social_media, study_group) очищаются явным null.
    @field_validator("first_name", "last_name", "phone_number", "email")
    @classmethod
    def forbid_null(cls, value):
        if value is None:
            raise ValueError("Поле не может быть null")
        return value


class PasswordChangeRequest(BaseModel):
    """Схема для смены пароля"""
    old_password: str = Field(..., min_length=8, max_length=64)
    new_password: str = Field(..., min_length=8, max_length=64)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=64)
