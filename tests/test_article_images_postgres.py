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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers

from psychohelp.config.config import config
from psychohelp.models.articles import Article
from psychohelp.repositories import articles as repository
from psychohelp.schemas.articles import ArticleResponse
from psychohelp.services import articles


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
    schema = "test_article_images_" + uuid4().hex
    admin = create_async_engine(url)
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    sessions = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Article.__table__.create)

        @asynccontextmanager
        async def get_db():
            async with sessions() as session:
                yield session

        monkeypatch.setattr(repository, "get_async_db", get_db)
        monkeypatch.setattr(config, "ARTICLE_IMAGE_DIR", tmp_path / "photos")
        article = await repository.create_article({"slug": "article", "title": "Заголовок", "text": "Текст"})
        yield SimpleNamespace(article=article, sessions=sessions)
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def test_persistent_photo_lifecycle(database):
    article_id = database.article.id
    first = await articles.upload_article_image(article_id, photo_upload())
    first_url = ArticleResponse.model_validate(first).image
    read = await repository.get_article_by_id(article_id)
    assert read.image == first_url
    second = await articles.upload_article_image(article_id, photo_upload())
    assert second.image != first_url
    assert [path.name for path in config.ARTICLE_IMAGE_DIR.iterdir()] == [second.image.rsplit("/", 1)[1]]
    image_with_query = second.image + "?v=1#preview"
    await articles.update_article(article_id, {"image": image_with_query})
    assert (await repository.get_article_by_id(article_id)).image == image_with_query
    assert [path.name for path in config.ARTICLE_IMAGE_DIR.iterdir()] == [second.image.rsplit("/", 1)[1]]
    changed = await articles.update_article(article_id, {"title": "Новый заголовок"})
    assert changed.image == image_with_query
    assert (await articles.update_article(article_id, {"image": None})).image is None
    assert not list(config.ARTICLE_IMAGE_DIR.iterdir())
    assert (await repository.get_article_by_id(article_id)).image is None
    await articles.upload_article_image(article_id, photo_upload())
    assert await articles.delete_article(article_id)
    assert await repository.get_article_by_id(article_id) is None
    assert not list(config.ARTICLE_IMAGE_DIR.iterdir())


async def test_concurrent_replacements_keep_only_the_committed_photo(database):
    article_id = database.article.id
    await articles.upload_article_image(article_id, photo_upload())
    results = await asyncio.gather(*[
        articles.upload_article_image(article_id, photo_upload()) for _ in range(6)
    ])
    assert len({result.image for result in results}) == 6
    current = await repository.get_article_by_id(article_id)
    assert [path.name for path in config.ARTICLE_IMAGE_DIR.iterdir()] == [current.image.rsplit("/", 1)[1]]


async def test_real_database_rollback_preserves_original_file(database, monkeypatch):
    article_id = database.article.id
    old_url = (await articles.upload_article_image(article_id, photo_upload())).image
    await repository.create_article({"slug": "duplicate", "title": "Другая статья", "text": "Текст"})
    original_update = repository.update_article_with_previous_image

    async def conflicting_update(article_id, data):
        return await original_update(article_id, data | {"slug": "duplicate"})

    monkeypatch.setattr(repository, "update_article_with_previous_image", conflicting_update)
    with pytest.raises(IntegrityError):
        await articles.upload_article_image(article_id, photo_upload())
    current = await repository.get_article_by_id(article_id)
    assert current.image == old_url
    assert current.slug == "article"
    assert [path.name for path in config.ARTICLE_IMAGE_DIR.iterdir()] == [old_url.rsplit("/", 1)[1]]


async def test_delete_during_file_processing_does_not_leave_new_photo(database, monkeypatch):
    article_id = database.article.id
    await articles.upload_article_image(article_id, photo_upload())
    stored = threading.Event()
    release = threading.Event()
    save = articles.save_article_image

    def delayed_save(*args):
        url = save(*args)
        stored.set()
        if not release.wait(10):
            raise AssertionError("The test did not release photo processing")
        return url

    monkeypatch.setattr(articles, "save_article_image", delayed_save)
    pending = asyncio.create_task(articles.upload_article_image(article_id, photo_upload()))
    try:
        assert await run_in_threadpool(stored.wait, 10)
        assert await articles.delete_article(article_id)
    finally:
        release.set()
    assert await asyncio.wait_for(pending, timeout=10) is None
    assert await repository.get_article_by_id(article_id) is None
    assert not list(config.ARTICLE_IMAGE_DIR.iterdir())
