from typing import Optional
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field
from psychohelp.models.psy_tests import TestType


class PsyTestCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    image: Optional[str] = Field(None, max_length=1024)
    type: TestType  # Обязательное поле при создании


class PsyTestUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, min_length=1)
    image: Optional[str] = Field(None, max_length=1024)
    type: Optional[TestType] = None


class PsyTestResponse(BaseModel):
    id: UUID
    title: str
    description: str
    image: Optional[str] = None
    type: TestType
    created_at: datetime

    class Config:
        from_attributes = True
