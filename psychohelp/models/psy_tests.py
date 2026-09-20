import uuid
import enum

from sqlalchemy import Column, String, Text, DateTime, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from psychohelp.config.config import Base


class TestType(str, enum.Enum):
    ENTERTAINING = "Развлекательный"
    MEDICAL = "Медицинский"


class PsyTest(Base):
    __tablename__ = "psychological_tests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    title = Column(String(255), nullable=False, comment="Название теста")
    description = Column(Text, nullable=False, comment="Описание теста")

    type = Column(Enum(TestType), nullable=False, comment="Тип теста: мед или развл")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)