"""add users.view_all permission

Revision ID: a7e1c2d3f4b5
Revises: 0cb1de8797bf
Create Date: 2026-10-06 00:00:00.000000

"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "a7e1c2d3f4b5"
down_revision: Union[str, Sequence[str], None] = "0cb1de8797bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PERMISSION_CODE = "USERS_VIEW_ALL"


def upgrade() -> None:
    conn = op.get_bind()

    with op.get_context().autocommit_block():
        op.execute(f"ALTER TYPE permissioncode ADD VALUE IF NOT EXISTS '{PERMISSION_CODE}'")

    conn.execute(
        sa.text(
            """
            INSERT INTO permissions (id, code, name, description, resource)
            VALUES (
                CAST(:id AS uuid),
                CAST(:code AS permissioncode),
                'Просмотр профилей пользователей',
                'Возможность просматривать полный профиль любого пользователя',
                'users'
            )
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                resource = EXCLUDED.resource
            """
        ),
        {"id": str(uuid4()), "code": PERMISSION_CODE},
    )

    conn.execute(
        sa.text(
            f"""
            INSERT INTO roles_permissions (role_id, permission_id)
            SELECT roles.id, permissions.id
            FROM roles
            CROSS JOIN permissions
            WHERE roles.code = CAST('ADMIN' AS rolecode)
              AND permissions.code = CAST('{PERMISSION_CODE}' AS permissioncode)
            ON CONFLICT DO NOTHING
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text(
            f"""
            DELETE FROM roles_permissions
            WHERE permission_id IN (
                SELECT id FROM permissions
                WHERE code = CAST('{PERMISSION_CODE}' AS permissioncode)
            )
            """
        )
    )
    conn.execute(
        sa.text(
            f"""
            DELETE FROM permissions
            WHERE code = CAST('{PERMISSION_CODE}' AS permissioncode)
            """
        )
    )
