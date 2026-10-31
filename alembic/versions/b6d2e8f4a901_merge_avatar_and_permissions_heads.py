"""merge avatar and permissions heads

Revision ID: b6d2e8f4a901
Revises: 09fd0153f8e6, a7e1c2d3f4b5
Create Date: 2026-10-25

"""
from typing import Sequence, Union


revision: str = "b6d2e8f4a901"
down_revision: Union[str, Sequence[str], None] = ("09fd0153f8e6", "a7e1c2d3f4b5")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge branches; schema changes are handled by the parent revisions."""
    pass


def downgrade() -> None:
    """Unmerge branches without changing the schema."""
    pass
