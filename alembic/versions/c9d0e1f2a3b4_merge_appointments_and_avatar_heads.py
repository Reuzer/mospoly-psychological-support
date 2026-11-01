"""merge appointments and avatar heads

Revision ID: c9d0e1f2a3b4
Revises: b6d2e8f4a901, b8c9d0e1f2a3
Create Date: 2026-11-01

"""
from typing import Sequence, Union


revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = ("b6d2e8f4a901", "b8c9d0e1f2a3")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge branches; schema changes are handled by the parent revisions."""
    pass


def downgrade() -> None:
    """Unmerge branches without changing the schema."""
    pass
