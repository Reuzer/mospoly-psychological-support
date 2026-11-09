from uuid import UUID

from sqlalchemy import select

from psychohelp.config.config import get_async_db
from psychohelp.models.news import News


async def get_news_list(skip: int = 0, take: int = 100) -> list[News]:
    async with get_async_db() as session:
        result = await session.execute(
            select(News)
            .order_by(News.event_date.desc())
            .offset(skip)
            .limit(take)
        )
        return list(result.scalars().all())


async def get_news_by_id(news_id: UUID) -> News | None:
    async with get_async_db() as session:
        result = await session.execute(
            select(News).where(News.id == news_id)
        )
        return result.scalar_one_or_none()


async def create_news(news_data: dict) -> News:
    async with get_async_db() as session:
        news_item = News(**news_data)
        session.add(news_item)
        await session.commit()
        await session.refresh(news_item)
        return news_item


async def update_news(news_id: UUID, news_data: dict) -> News | None:
    news_item, _ = await update_news_with_previous_image(news_id, news_data)
    return news_item


async def update_news_with_previous_image(
    news_id: UUID, news_data: dict,
) -> tuple[News | None, str | None]:
    if not news_data:
        return await get_news_by_id(news_id), None

    async with get_async_db() as session:
        result = await session.execute(
            select(News)
            .where(News.id == news_id)
            .with_for_update()
        )
        news_item = result.scalar_one_or_none()
        if news_item is None:
            return None, None
        previous_image = news_item.image
        for field, value in news_data.items():
            setattr(news_item, field, value)
        await session.commit()
        return news_item, previous_image


async def delete_news(news_id: UUID) -> bool:
    deleted, _ = await delete_news_with_previous_image(news_id)
    return deleted


async def delete_news_with_previous_image(news_id: UUID) -> tuple[bool, str | None]:
    async with get_async_db() as session:
        result = await session.execute(
            select(News).where(News.id == news_id).with_for_update()
        )
        news_item = result.scalar_one_or_none()
        if news_item is None:
            return False, None

        previous_image = news_item.image
        await session.delete(news_item)
        await session.commit()
        return True, previous_image
