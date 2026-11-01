"""remove applications and bind time slots to appointments

Revision ID: b8c9d0e1f2a3
Revises: a7e1c2d3f4b5
Create Date: 2026-10-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects import postgresql


revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7e1c2d3f4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(bind: sa.Connection, table: str) -> set[str]:
    inspector = sa_inspect(bind)
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def _drop_application_fk(bind: sa.Connection) -> None:
    inspector = sa_inspect(bind)
    for foreign_key in inspector.get_foreign_keys("appointments"):
        if foreign_key.get("constrained_columns") == ["application_id"]:
            op.drop_constraint(foreign_key["name"], "appointments", type_="foreignkey")


def _migrate_legacy_applications(bind: sa.Connection) -> None:
    if not sa_inspect(bind).has_table("applications"):
        return

    appointment_columns = _column_names(bind, "appointments")
    snapshot_columns = ""
    snapshot_values = ""
    if {"patient_first_name", "patient_last_name"}.issubset(appointment_columns):
        snapshot_columns = ", patient_first_name, patient_last_name"
        snapshot_values = ", first_name, last_name"

    op.execute(
        sa.text(
            f"""
            WITH candidates AS (
                SELECT
                    a.id,
                    a.user_id,
                    a.psychologist_id,
                    CASE
                        WHEN lower(COALESCE(a.meeting_type, 'offline')) = 'online'
                            THEN 'Online'
                        ELSE 'Offline'
                    END AS appointment_type,
                    a.problem_description,
                    CASE
                        WHEN a.status IN ('cancelled', 'rejected', 'expired')
                            THEN 'cancelled'
                        WHEN a.status = 'completed'
                            THEN 'done'
                        ELSE 'awaiting'
                    END AS appointment_status,
                    COALESCE(a.cancel_reason, a.reject_reason) AS cancel_reason,
                    CASE
                        WHEN a.cancel_initiator = 'user' THEN 'patient'
                        WHEN a.cancel_initiator = 'psychologist' THEN 'psychologist'
                        ELSE NULL
                    END AS cancelled_by,
                    a.scheduled_at,
                    COALESCE(a.updated_at, a.created_at, CURRENT_TIMESTAMP) AS changed_at,
                    COALESCE(
                        CASE
                            WHEN lower(COALESCE(a.meeting_type, 'offline')) = 'online'
                                THEN a.meeting_url
                            ELSE a.location_address
                        END,
                        p.office,
                        'Не указано'
                    ) AS venue,
                    a.internal_comment,
                    u.first_name,
                    u.last_name,
                    row_number() OVER (
                        PARTITION BY a.psychologist_id, a.scheduled_at
                        ORDER BY a.created_at, a.id
                    ) AS slot_number
                FROM applications AS a
                JOIN users AS u ON u.id = a.user_id
                JOIN psychologists AS p ON p.id = a.psychologist_id
                WHERE a.appointment_id IS NULL
                  AND a.user_id IS NOT NULL
                  AND a.psychologist_id IS NOT NULL
                  AND a.scheduled_at IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM appointments AS existing
                      WHERE existing.application_id = a.id
                         OR existing.id = a.id
                  )
            )
            INSERT INTO appointments (
                id,
                patient_id,
                psychologist_id,
                type,
                duration,
                reason,
                status,
                cancel_reason,
                cancelled_by,
                emergency_cancellation,
                conclusion,
                psychologist_comment,
                scheduled_time,
                remind_time,
                last_change_time,
                venue,
                comment,
                emergency_contact
                {snapshot_columns}
            )
            SELECT
                id,
                user_id,
                psychologist_id,
                appointment_type::appointmenttype,
                60,
                problem_description,
                appointment_status::appointmentstatus,
                cancel_reason,
                cancelled_by,
                FALSE,
                NULL,
                internal_comment,
                scheduled_at,
                NULL,
                changed_at,
                venue,
                NULL,
                NULL
                {snapshot_values}
            FROM candidates
            WHERE slot_number = 1
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column(
        "appointments",
        sa.Column("duration", sa.Integer(), nullable=False, server_default="60"),
    )
    op.add_column(
        "appointments",
        sa.Column("cancelled_by", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "appointments",
        sa.Column(
            "emergency_cancellation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column(
        "appointments",
        "reason",
        existing_type=sa.String(length=64),
        type_=sa.Text(),
        existing_nullable=True,
    )

    _migrate_legacy_applications(bind)

    if "application_id" in _column_names(bind, "appointments"):
        _drop_application_fk(bind)
        op.drop_index("ix_appointments_application_id", table_name="appointments", if_exists=True)
        op.drop_column("appointments", "application_id")

    op.drop_table("application_audit_logs", if_exists=True)
    op.drop_table("applications", if_exists=True)

    op.create_index(
        "uq_appointments_psychologist_scheduled_active",
        "appointments",
        ["psychologist_id", "scheduled_time"],
        unique=True,
        postgresql_where=sa.text("status = 'awaiting'::appointmentstatus"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_appointments_psychologist_scheduled_active",
        table_name="appointments",
    )

    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("problem_description", sa.Text(), nullable=False),
        sa.Column("preferred_campus", sa.String(length=128), nullable=True),
        sa.Column("university_status", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="new"),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("psychologist_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("meeting_type", sa.String(length=20), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location_address", sa.Text(), nullable=True),
        sa.Column("meeting_url", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmation_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("cancel_initiator", sa.String(length=20), nullable=True),
        sa.Column("internal_comment", sa.Text(), nullable=True),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["psychologist_id"], ["psychologists.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_applications_id", "applications", ["id"])
    op.create_index("ix_applications_user_id", "applications", ["user_id"])
    op.create_index("ix_applications_status", "applications", ["status"])
    op.create_index("ix_applications_assigned_to", "applications", ["assigned_to"])

    op.create_table(
        "application_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("previous_status", sa.String(length=50), nullable=True),
        sa.Column("new_status", sa.String(length=50), nullable=False),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("comment", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_application_audit_logs_application_id",
        "application_audit_logs",
        ["application_id"],
    )

    op.add_column(
        "appointments",
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_appointments_application_id",
        "appointments",
        ["application_id"],
    )
    op.create_foreign_key(
        "appointments_application_id_fkey",
        "appointments",
        "applications",
        ["application_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.alter_column(
        "appointments",
        "reason",
        existing_type=sa.Text(),
        type_=sa.String(length=64),
        existing_nullable=True,
        postgresql_using="left(reason, 64)",
    )
    op.drop_column("appointments", "emergency_cancellation")
    op.drop_column("appointments", "cancelled_by")
    op.drop_column("appointments", "duration")
