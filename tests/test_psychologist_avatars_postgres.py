"""PostgreSQL integration tests for psychologist photo synchronization.

The tests use only a disposable database supplied explicitly through
PSYCHOHELP_TEST_DATABASE_URL.
"""

import importlib.util
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import psychohelp.models  # noqa: F401
from psychohelp.config.config import Base
from psychohelp.constants.rbac import RoleCode
from psychohelp.models.psychologists import Psychologist
from psychohelp.models.roles import Role
from psychohelp.models.users import User
from psychohelp.repositories import users as users_repo
from psychohelp.repositories.psychologists import psychologists as psychologists_repo


@pytest.fixture
async def database(monkeypatch):
    url = os.getenv("PSYCHOHELP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set PSYCHOHELP_TEST_DATABASE_URL to run PostgreSQL integration tests")

    schema = "test_psychologist_avatars_" + uuid4().hex
    admin = create_async_engine(url, poolclass=NullPool)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = create_async_engine(
        url,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema}},
    )
    sessions = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def get_db():
        async with sessions() as session:
            yield session

    monkeypatch.setattr(users_repo, "get_async_db", get_db)
    monkeypatch.setattr(psychologists_repo, "get_async_db", get_db)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield sessions
    finally:
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()
        await admin.dispose()


def make_user(avatar=None):
    return User(
        first_name="Тест",
        last_name="Тестов",
        phone_number="+79991234567",
        email=f"{uuid4().hex}@example.com",
        password="test",
        avatar=avatar,
    )


def psychologist_data():
    return {
        "experience": "5 лет",
        "qualification": "Психолог",
        "consult_areas": "Стресс",
        "description": "Описание",
        "office": "Кабинет 1",
        "education": "Высшее",
        "short_description": "Психолог",
    }


async def test_set_avatar_synchronizes_linked_psychologist(database):
    async with database() as session:
        psychologist_user = make_user()
        regular_user = make_user()
        session.add_all([psychologist_user, regular_user])
        await session.flush()
        psychologist = Psychologist(
            user_id=psychologist_user.id,
            **psychologist_data(),
            photo="old.webp",
        )
        session.add(psychologist)
        await session.commit()
        psychologist_id = psychologist.id

    await users_repo.set_avatar("new.webp", psychologist_user)
    await users_repo.set_avatar("regular.webp", regular_user)

    async with database() as session:
        updated_psychologist = await session.get(Psychologist, psychologist_id)
        assert updated_psychologist.photo == "new.webp"
        assert (await session.get(User, psychologist_user.id)).avatar == "new.webp"
        assert (await session.get(User, regular_user.id)).avatar == "regular.webp"


@pytest.mark.parametrize("avatar", ["existing.webp", None])
async def test_create_psychologist_copies_user_avatar(database, avatar):
    async with database() as session:
        user = make_user(avatar=avatar)
        session.add(user)
        session.add(Role(code=RoleCode.PSYCHOLOGIST, name="Психолог"))
        await session.commit()

    psychologist = await psychologists_repo.create_psychologist(
        user.id,
        {**psychologist_data(), "photo": "must-not-be-used.webp"},
    )

    assert psychologist.photo == avatar
    async with database() as session:
        stored = await session.scalar(
            select(Psychologist).where(Psychologist.user_id == user.id)
        )
        assert stored.photo == avatar


@pytest.mark.parametrize(
    ("avatar", "expected_photo"), [(None, "old.webp"), ("avatar.webp", "avatar.webp")]
)
async def test_migration_preserves_existing_photo_when_user_has_no_avatar(
    database, avatar, expected_photo
):
    migration_path = (
        Path(__file__).parents[1]
        / "alembic/versions/e4f5a6b7c8d9_sync_psychologist_photos_with_user_avatars.py"
    )
    spec = importlib.util.spec_from_file_location("psychologist_avatar_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def upgrade(connection):
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

    async with database() as session:
        user = make_user(avatar=avatar)
        session.add(user)
        await session.flush()
        psychologist = Psychologist(user_id=user.id, photo="old.webp", **psychologist_data())
        session.add(psychologist)
        await session.commit()

        connection = await session.connection()
        await connection.run_sync(upgrade)
        await session.commit()

    async with database() as session:
        stored_photo = await session.scalar(
            select(Psychologist.photo).where(Psychologist.id == psychologist.id)
        )
        assert stored_photo == expected_photo
