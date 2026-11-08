from uuid import UUID

from sqlalchemy import select

from psychohelp.config.config import get_async_db
from psychohelp.models.articles import Article


async def get_articles(skip: int = 0, take: int = 100) -> list[Article]:
    async with get_async_db() as session:
        result = await session.execute(
            select(Article)
            .order_by(Article.title.asc())
            .offset(skip)
            .limit(take)
        )
        return list(result.scalars().all())


async def get_article_by_id(article_id: UUID) -> Article | None:
    async with get_async_db() as session:
        result = await session.execute(
            select(Article).where(Article.id == article_id)
        )
        return result.scalar_one_or_none()


async def create_article(article_data: dict) -> Article:
    async with get_async_db() as session:
        article = Article(**article_data)
        session.add(article)
        await session.commit()
        await session.refresh(article)
        return article


async def update_article_with_previous_image(
    article_id: UUID, article_data: dict,
) -> tuple[Article | None, str | None]:
    if not article_data:
        return await get_article_by_id(article_id), None

    async with get_async_db() as session:
        result = await session.execute(
            select(Article)
            .where(Article.id == article_id)
            .with_for_update()
        )
        article = result.scalar_one_or_none()
        if article is None:
            return None, None
        previous_image = article.image
        for field, value in article_data.items():
            setattr(article, field, value)
        await session.commit()
        return article, previous_image


async def delete_article_with_previous_image(article_id: UUID) -> tuple[bool, str | None]:
    async with get_async_db() as session:
        result = await session.execute(
            select(Article).where(Article.id == article_id).with_for_update()
        )
        article = result.scalar_one_or_none()
        if article is None:
            return False, None

        previous_image = article.image
        await session.delete(article)
        await session.commit()
        return True, previous_image
