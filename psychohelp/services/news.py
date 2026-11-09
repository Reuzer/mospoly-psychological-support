from uuid import UUID

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from psychohelp.models.news import News
from psychohelp.repositories import news as news_repo
from psychohelp.services.news_images import (
    MAX_IMAGE_SIZE,
    remove_news_image,
    save_news_image,
)


async def get_news_list(skip: int = 0, take: int = 100) -> list[News]:
    return await news_repo.get_news_list(skip, take)


async def get_news_by_id(news_id: UUID) -> News | None:
    return await news_repo.get_news_by_id(news_id)


async def create_news(news_data: dict) -> News:
    return await news_repo.create_news(news_data)


async def update_news(news_id: UUID, news_data: dict) -> News | None:
    news_item, previous_image = await news_repo.update_news_with_previous_image(news_id, news_data)
    if news_item is not None and "image" in news_data and previous_image != news_item.image:
        await run_in_threadpool(remove_news_image, news_id, previous_image)
    return news_item


async def upload_news_image(news_id: UUID, image: UploadFile) -> News | None:
    try:
        if await news_repo.get_news_by_id(news_id) is None:
            return None
        contents = await image.read(MAX_IMAGE_SIZE + 1)
        image_url = await run_in_threadpool(save_news_image, news_id, contents, image.content_type)
    finally:
        await image.close()

    try:
        news_item = await update_news(news_id, {"image": image_url})
    except Exception:
        await run_in_threadpool(remove_news_image, news_id, image_url)
        raise
    if news_item is None:
        # Новость могли удалить во время обработки файла.
        await run_in_threadpool(remove_news_image, news_id, image_url)
    return news_item


async def delete_news(news_id: UUID) -> bool:
    deleted, previous_image = await news_repo.delete_news_with_previous_image(news_id)
    if deleted:
        await run_in_threadpool(remove_news_image, news_id, previous_image)
    return deleted
