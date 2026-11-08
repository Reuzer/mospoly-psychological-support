from typing import Optional
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ArticleCreateRequest(BaseModel):
    slug: str = Field(..., min_length=1, max_length=255)
    image: Optional[str] = Field(None, max_length=1024)
    date: Optional[datetime] = None
    author: Optional[str] = Field(None, max_length=255)
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    text: str = Field(..., min_length=1)


class ArticleUpdateRequest(BaseModel):
    slug: Optional[str] = Field(None, min_length=1, max_length=255)
    image: Optional[str] = Field(None, max_length=1024)
    date: Optional[datetime] = None
    author: Optional[str] = Field(None, max_length=255)
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    text: Optional[str] = Field(None, min_length=1)

    # Обязательные поля можно не передавать, но нельзя очистить через null.
    # Остальные (image, date, author, description) очищаются явным null.
    @field_validator("slug", "title", "text")
    @classmethod
    def forbid_null(cls, value):
        if value is None:
            raise ValueError("Поле не может быть null")
        return value


class ArticleResponse(BaseModel):
    id: UUID
    slug: str
    image: Optional[str]
    date: Optional[datetime]
    author: Optional[str]
    title: str
    description: Optional[str]
    text: str

    class Config:
        from_attributes = True
