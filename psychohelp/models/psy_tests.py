import uuid
import enum

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, Enum, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint, false, text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from psychohelp.config.config import Base


class TestType(str, enum.Enum):
    ENTERTAINING = "Развлекательный"
    MEDICAL = "Медицинский"


class QuestionType(str, enum.Enum):
    TEXT = "text"
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"


class PsyTest(Base):
    __tablename__ = "psychological_tests"
    __table_args__ = (
        CheckConstraint("estimated_duration_minutes > 0", name="ck_psy_tests_estimated_duration"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    title = Column(String(255), nullable=False, comment="Название теста")
    description = Column(Text, nullable=False, comment="Описание теста")
    image = Column(String(1024), nullable=True, comment="Ссылка на фотографию теста")
    url = Column(String(2083), nullable=True, comment="Ссылка на внешний развлекательный тест")
    archived = Column(Boolean, nullable=False, server_default=false())
    estimated_duration_minutes = Column(Integer, nullable=True)

    type = Column(Enum(TestType), nullable=False, comment="Тип теста: мед или развл")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PsyTestQuestion(Base):
    __tablename__ = "psy_test_questions"
    __table_args__ = (
        UniqueConstraint("test_id", "position", name="uq_psy_test_questions_test_position"),
        CheckConstraint("position > 0", name="ck_psy_test_questions_position"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    test_id = Column(
        UUID(as_uuid=True), ForeignKey("psychological_tests.id", ondelete="CASCADE"), nullable=False,
    )
    position = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    image = Column(String(1024), nullable=True)
    type = Column(
        Enum(
            QuestionType, name="ck_psy_test_questions_type", native_enum=False,
            create_constraint=True, values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False, server_default=QuestionType.TEXT.value,
    )
    options = relationship(
        "PsyTestQuestionOption", order_by="PsyTestQuestionOption.position",
        cascade="all, delete-orphan", passive_deletes=True, lazy="raise",
    )


class PsyTestQuestionOption(Base):
    __tablename__ = "psy_test_question_options"
    __table_args__ = (
        UniqueConstraint("question_id", "position", name="uq_psy_test_question_options_position"),
        CheckConstraint("position > 0", name="ck_psy_test_question_options_position"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id = Column(
        UUID(as_uuid=True), ForeignKey("psy_test_questions.id", ondelete="CASCADE"), nullable=False,
    )
    position = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)


class PsyTestAttempt(Base):
    __tablename__ = "psy_test_attempts"
    __table_args__ = (
        Index("ix_psy_test_attempts_test", "test_id"),
        Index("ix_psy_test_attempts_user_started", "user_id", "started_at", "id"),
        Index(
            "uq_psy_test_attempts_in_progress", "test_id", "user_id", unique=True,
            postgresql_where=text("completed_at IS NULL"),
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    test_id = Column(
        UUID(as_uuid=True), ForeignKey("psychological_tests.id", ondelete="CASCADE"), nullable=False,
    )
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class PsyTestAnswer(Base):
    __tablename__ = "psy_test_answers"
    __table_args__ = (
        CheckConstraint(
            "(answer IS NOT NULL AND option_ids IS NULL) OR "
            "(answer IS NULL AND option_ids IS NOT NULL AND cardinality(option_ids) > 0)",
            name="ck_psy_test_answers_value",
        ),
    )

    attempt_id = Column(
        UUID(as_uuid=True), ForeignKey("psy_test_attempts.id", ondelete="CASCADE"), primary_key=True,
    )
    question_id = Column(
        UUID(as_uuid=True), ForeignKey("psy_test_questions.id", ondelete="CASCADE"),
        primary_key=True, index=True,
    )
    answer = Column(Text, nullable=True)
    option_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=True)
    answered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
