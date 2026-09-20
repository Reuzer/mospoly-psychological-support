from uuid import UUID

from sqlalchemy import select, update

from psychohelp.config.config import get_async_db
from psychohelp.models.psy_tests import PsyTest


async def get_PsyTest_list(skip: int = 0, take: int = 100) -> list[PsyTest]:
    async with get_async_db() as session:
        result = await session.execute(
            select(PsyTest)
            .order_by(PsyTest.created_at.desc())
            .offset(skip)
            .limit(take)
        )
        return list(result.scalars().all())


async def get_PsyTest_by_id(PsyTest_id: UUID) -> PsyTest | None:
    async with get_async_db() as session:
        result = await session.execute(
            select(PsyTest).where(PsyTest.id == PsyTest_id)
        )
        return result.scalar_one_or_none()


async def create_PsyTest(PsyTest_data: dict) -> PsyTest:
    async with get_async_db() as session:
        PsyTest_item = PsyTest(**PsyTest_data)
        session.add(PsyTest_item)
        await session.commit()
        await session.refresh(PsyTest_item)
        return PsyTest_item


async def update_PsyTest(PsyTest_id: UUID, PsyTest_data: dict) -> PsyTest | None:
    async with get_async_db() as session:
        stmt = (
            update(PsyTest)
            .where(PsyTest.id == PsyTest_id)
            .values(**PsyTest_data)
            .returning(PsyTest)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one_or_none()


async def delete_PsyTest(PsyTest_id: UUID) -> bool:
    async with get_async_db() as session:
        PsyTest_item = await session.get(PsyTest, PsyTest_id)
        if PsyTest_item is None:
            return False

        await session.delete(PsyTest_item)
        await session.commit()
        return True