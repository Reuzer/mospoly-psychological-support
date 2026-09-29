"""Add emergency contact to appointments.

Revision ID: f3a4b5c6d7e8
Revises: c8f9e0a1b2c3
"""
from alembic import op
import sqlalchemy as sa

revision = "f3a4b5c6d7e8"
down_revision = "c8f9e0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("emergency_contact", sa.String(512), nullable=True, comment="Экстренный контакт"),
    )


def downgrade() -> None:
    op.drop_column("appointments", "emergency_contact")
