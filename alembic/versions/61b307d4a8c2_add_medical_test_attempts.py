"""Добавить вопросы, ответы и прохождения медицинских тестов.

Revision ID: 61b307d4a8c2
Revises: f7a8b9c0d1e2
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "61b307d4a8c2"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "psychological_tests",
        sa.Column("url", sa.String(2083), nullable=True, comment="Ссылка на внешний развлекательный тест"),
    )
    op.add_column(
        "psychological_tests",
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "psy_test_questions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "test_id", sa.Uuid(), sa.ForeignKey("psychological_tests.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("image", sa.String(1024), nullable=True),
        sa.Column(
            "type",
            sa.Enum(
                "text", "single_choice", "multiple_choice",
                name="ck_psy_test_questions_type", native_enum=False, create_constraint=True,
            ),
            nullable=False, server_default="text",
        ),
        sa.UniqueConstraint("test_id", "position", name="uq_psy_test_questions_test_position"),
        sa.CheckConstraint("position > 0", name="ck_psy_test_questions_position"),
    )
    op.create_table(
        "psy_test_question_options",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "question_id", sa.Uuid(), sa.ForeignKey("psy_test_questions.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.UniqueConstraint("question_id", "position", name="uq_psy_test_question_options_position"),
        sa.CheckConstraint("position > 0", name="ck_psy_test_question_options_position"),
    )
    op.create_table(
        "psy_test_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "test_id", sa.Uuid(), sa.ForeignKey("psychological_tests.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_psy_test_attempts_test", "psy_test_attempts", ["test_id"])
    op.create_index("ix_psy_test_attempts_user_started", "psy_test_attempts", ["user_id", "started_at", "id"])
    op.create_index(
        "uq_psy_test_attempts_in_progress", "psy_test_attempts", ["test_id", "user_id"],
        unique=True, postgresql_where=sa.text("completed_at IS NULL"),
    )
    op.create_table(
        "psy_test_answers",
        sa.Column(
            "attempt_id", sa.Uuid(), sa.ForeignKey("psy_test_attempts.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "question_id", sa.Uuid(), sa.ForeignKey("psy_test_questions.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("option_ids", postgresql.ARRAY(sa.Uuid()), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "(answer IS NOT NULL AND option_ids IS NULL) OR "
            "(answer IS NULL AND option_ids IS NOT NULL AND cardinality(option_ids) > 0)",
            name="ck_psy_test_answers_value",
        ),
    )
    op.create_index("ix_psy_test_answers_question_id", "psy_test_answers", ["question_id"])


def downgrade() -> None:
    op.drop_table("psy_test_answers")
    op.drop_table("psy_test_attempts")
    op.drop_table("psy_test_question_options")
    op.drop_table("psy_test_questions")
    op.drop_column("psychological_tests", "archived")
    op.drop_column("psychological_tests", "url")
