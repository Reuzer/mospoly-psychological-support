from uuid import UUID

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from psychohelp.models.articles import Article
from psychohelp.repositories import articles as repo
from psychohelp.services.article_images import (
    MAX_IMAGE_SIZE,
    remove_article_image,
    save_article_image,
)


async def get_articles(skip: int = 0, take: int = 100) -> list[Article]:
    return await repo.get_articles(skip=skip, take=take)


async def get_article_by_id(article_id: UUID) -> Article | None:
    return await repo.get_article_by_id(article_id)


async def create_article(article_data: dict) -> Article:
    return await repo.create_article(article_data)


async def update_article(article_id: UUID, article_data: dict) -> Article | None:
    article, previous_image = await repo.update_article_with_previous_image(article_id, article_data)
    if article is not None and "image" in article_data and previous_image != article.image:
        await run_in_threadpool(remove_article_image, article_id, previous_image)
    return article


async def upload_article_image(article_id: UUID, image: UploadFile) -> Article | None:
    try:
        if await repo.get_article_by_id(article_id) is None:
            return None
        # Ограничиваем чтение, даже если Content-Length отсутствует или намеренно искажён
        contents = await image.read(MAX_IMAGE_SIZE + 1)
        image_url = await run_in_threadpool(save_article_image, article_id, contents, image.content_type)
    finally:
        await image.close()

    try:
        article = await update_article(article_id, {"image": image_url})
    except Exception:
        await run_in_threadpool(remove_article_image, article_id, image_url)
        raise
    if article is None:
        # Статью могли удалить во время обработки файла
        await run_in_threadpool(remove_article_image, article_id, image_url)
    return article


async def delete_article(article_id: UUID) -> bool:
    deleted, previous_image = await repo.delete_article_with_previous_image(article_id)
    if deleted:
        await run_in_threadpool(remove_article_image, article_id, previous_image)
    return deleted
