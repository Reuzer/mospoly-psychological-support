"""Добавить продолжительность теста и статус неявки.

Revision ID: c2a670d85b19
Revises: 61b307d4a8c2
"""

import sqlalchemy as sa
from alembic import op


revision = "c2a670d85b19"
down_revision = "61b307d4a8c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("psychological_tests", sa.Column("estimated_duration_minutes", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_psy_tests_estimated_duration", "psychological_tests", "estimated_duration_minutes > 0",
    )
    op.execute("ALTER TYPE appointmentstatus ADD VALUE IF NOT EXISTS 'no_show'")


def downgrade() -> None:
    op.drop_index("uq_appointments_psychologist_scheduled_active", table_name="appointments")
    op.execute("ALTER TYPE appointmentstatus RENAME TO appointmentstatus_with_no_show")
    op.execute("CREATE TYPE appointmentstatus AS ENUM ('awaiting', 'cancelled', 'done')")
    op.execute(
        """
        ALTER TABLE appointments ALTER COLUMN status TYPE appointmentstatus
        USING (CASE WHEN status::text = 'no_show' THEN 'cancelled' ELSE status::text END)::appointmentstatus
        """
    )
    op.execute("DROP TYPE appointmentstatus_with_no_show")
    op.create_index(
        "uq_appointments_psychologist_scheduled_active",
        "appointments",
        ["psychologist_id", "scheduled_time"],
        unique=True,
        postgresql_where=sa.text("status = 'awaiting'::appointmentstatus"),
    )
    op.drop_constraint("ck_psy_tests_estimated_duration", "psychological_tests", type_="check")
    op.drop_column("psychological_tests", "estimated_duration_minutes")
