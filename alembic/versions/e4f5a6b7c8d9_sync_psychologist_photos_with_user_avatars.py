"""sync psychologist photos with user avatars

Revision ID: e4f5a6b7c8d9
Revises: d5e6f7a8b9c0
Create Date: 2026-11-15

"""
from typing import Sequence, Union

from alembic import op


revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE psychologists
        SET photo = users.avatar
        FROM users
        WHERE psychologists.user_id = users.id
        """
    )


def downgrade() -> None:
    # Previous psychologist-specific photos cannot be restored after the sync.
    pass
