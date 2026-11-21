"""Добавить общую заметку пациента и хранение завершённых прохождений.

Revision ID: a6b7c8d9e0f1
Revises: d5e6f7a8b9c0
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a6b7c8d9e0f1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("note", sa.Text(), nullable=True, comment="Общая заметка психологов о пациенте"),
    )
    op.add_column(
        "users",
        sa.Column(
            "note_version", sa.Integer(), nullable=False, server_default=sa.text("0"),
            comment="Версия общей заметки психологов",
        ),
    )
    op.create_check_constraint("ck_users_note_version_nonnegative", "users", "note_version >= 0")
    op.create_table(
        "psy_test_completions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "test_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("psychological_tests.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "completed_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_psy_test_completions_user_test", "psy_test_completions", ["user_id", "test_id"])
    op.create_table(
        "survey_completions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("survey_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "completed_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_survey_completions_user_survey", "survey_completions", ["user_id", "survey_id"])
    # Медкарта ищет приёмы пациента по статусу, затем по времени и ID.
    op.create_index(
        "ix_appointments_patient_status_time_id", "appointments",
        ["patient_id", "status", "scheduled_time", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_appointments_patient_status_time_id", table_name="appointments")
    op.drop_table("survey_completions")
    op.drop_table("psy_test_completions")
    op.drop_constraint("ck_users_note_version_nonnegative", "users", type_="check")
    op.drop_column("users", "note_version")
    op.drop_column("users", "note")
