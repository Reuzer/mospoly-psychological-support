import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from psychohelp.config.config import Base


class PsyTestCompletion(Base):
    """Завершённое прохождение теста. Повторные прохождения сохраняются отдельно."""

    __tablename__ = "psy_test_completions"
    __table_args__ = (Index("ix_psy_test_completions_user_test", "user_id", "test_id"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    test_id = Column(
        UUID(as_uuid=True), ForeignKey("psychological_tests.id", ondelete="CASCADE"),
        nullable=False,
    )
    completed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SurveyCompletion(Base):
    """Завершённое прохождение опроса, идентифицируемого по survey_id."""

    __tablename__ = "survey_completions"
    __table_args__ = (Index("ix_survey_completions_user_survey", "user_id", "survey_id"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    # Каталога опросов в проекте пока нет; сохраняем идентификатор источника.
    survey_id = Column(UUID(as_uuid=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
