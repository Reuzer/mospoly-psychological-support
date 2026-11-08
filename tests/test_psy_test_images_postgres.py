import asyncio
import io
import os
import threading
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import UploadFile
from PIL import Image
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers

from psychohelp.config.config import config
from psychohelp.models.psy_tests import PsyTest, TestType
from psychohelp.repositories import psy_tests as repository
from psychohelp.schemas.psy_tests import PsyTestResponse
from psychohelp.services import psy_tests


def photo_upload():
    contents = io.BytesIO()
    with Image.new("RGB", (16, 12), "blue") as image:
        image.save(contents, "PNG")
    contents.seek(0)
    return UploadFile(contents, filename="photo.png", headers=Headers({"content-type": "image/png"}))


@pytest_asyncio.fixture(loop_scope="function")
async def database(monkeypatch, tmp_path):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for isolated PostgreSQL tests")
    schema = "test_psy_test_images_" + uuid4().hex
    admin = create_async_engine(url)
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    sessions = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        async with engine.begin() as connection:
            await connection.run_sync(PsyTest.__table__.create)

        @asynccontextmanager
        async def get_db():
            async with sessions() as session:
                yield session

        monkeypatch.setattr(repository, "get_async_db", get_db)
        monkeypatch.setattr(config, "ARTICLE_IMAGE_DIR", tmp_path / "photos")
        psy_test = await repository.create_psy_test(
            {"title": "Тест", "description": "Описание", "type": TestType.MEDICAL},
        )
        yield SimpleNamespace(psy_test=psy_test, sessions=sessions)
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def test_persistent_photo_lifecycle(database):
    psy_test_id = database.psy_test.id
    first = await psy_tests.upload_psy_test_image(psy_test_id, photo_upload())
    first_url = PsyTestResponse.model_validate(first).image
    read = await repository.get_psy_test_by_id(psy_test_id)
    assert read.image == first_url
    second = await psy_tests.upload_psy_test_image(psy_test_id, photo_upload())
    assert second.image != first_url
    assert [path.name for path in config.PSY_TEST_IMAGE_DIR.iterdir()] == [second.image.rsplit("/", 1)[1]]
    changed = await psy_tests.update_psy_test(psy_test_id, {"title": "Новый заголовок"})
    assert changed.image == second.image
    assert (await psy_tests.update_psy_test(psy_test_id, {"image": None})).image is None
    assert not list(config.PSY_TEST_IMAGE_DIR.iterdir())
    assert (await repository.get_psy_test_by_id(psy_test_id)).image is None
    await psy_tests.upload_psy_test_image(psy_test_id, photo_upload())
    assert await psy_tests.delete_psy_test(psy_test_id)
    assert await repository.get_psy_test_by_id(psy_test_id) is None
    assert not list(config.PSY_TEST_IMAGE_DIR.iterdir())


async def test_concurrent_replacements_keep_only_the_committed_photo(database):
    psy_test_id = database.psy_test.id
    await psy_tests.upload_psy_test_image(psy_test_id, photo_upload())
    results = await asyncio.gather(*[
        psy_tests.upload_psy_test_image(psy_test_id, photo_upload()) for _ in range(6)
    ])
    assert len({result.image for result in results}) == 6
    current = await repository.get_psy_test_by_id(psy_test_id)
    assert [path.name for path in config.PSY_TEST_IMAGE_DIR.iterdir()] == [current.image.rsplit("/", 1)[1]]


async def test_real_database_rollback_preserves_original_file(database, monkeypatch):
    psy_test_id = database.psy_test.id
    old_url = (await psy_tests.upload_psy_test_image(psy_test_id, photo_upload())).image
    original_update = repository.update_psy_test_with_previous_image

    async def failing_update(psy_test_id, data):
        # Заголовок длиннее 255 символов отклоняется самой PostgreSQL
        return await original_update(psy_test_id, data | {"title": "x" * 256})

    monkeypatch.setattr(repository, "update_psy_test_with_previous_image", failing_update)
    with pytest.raises(DBAPIError):
        await psy_tests.upload_psy_test_image(psy_test_id, photo_upload())
    current = await repository.get_psy_test_by_id(psy_test_id)
    assert current.image == old_url
    assert current.title == "Тест"
    assert [path.name for path in config.PSY_TEST_IMAGE_DIR.iterdir()] == [old_url.rsplit("/", 1)[1]]


async def test_delete_during_file_processing_does_not_leave_new_photo(database, monkeypatch):
    psy_test_id = database.psy_test.id
    await psy_tests.upload_psy_test_image(psy_test_id, photo_upload())
    stored = threading.Event()
    release = threading.Event()
    save = psy_tests.save_psy_test_image

    def delayed_save(*args):
        url = save(*args)
        stored.set()
        if not release.wait(10):
            raise AssertionError("The test did not release photo processing")
        return url

    monkeypatch.setattr(psy_tests, "save_psy_test_image", delayed_save)
    pending = asyncio.create_task(psy_tests.upload_psy_test_image(psy_test_id, photo_upload()))
    try:
        assert await run_in_threadpool(stored.wait, 10)
        assert await psy_tests.delete_psy_test(psy_test_id)
    finally:
        release.set()
    assert await asyncio.wait_for(pending, timeout=10) is None
    assert await repository.get_psy_test_by_id(psy_test_id) is None
    assert not list(config.PSY_TEST_IMAGE_DIR.iterdir())
