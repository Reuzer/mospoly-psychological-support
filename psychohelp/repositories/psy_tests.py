from uuid import UUID

from sqlalchemy import select, update

from psychohelp.config.config import get_async_db
from psychohelp.models.psy_tests import PsyTest


async def get_psy_test_list(skip: int = 0, take: int = 100) -> list[PsyTest]:
    async with get_async_db() as session:
        result = await session.execute(
            select(PsyTest)
            .order_by(PsyTest.created_at.desc())
            .offset(skip)
            .limit(take)
        )
        return list(result.scalars().all())


async def get_psy_test_by_id(psy_test_id: UUID) -> PsyTest | None:
    async with get_async_db() as session:
        result = await session.execute(
            select(PsyTest).where(PsyTest.id == psy_test_id)
        )
        return result.scalar_one_or_none()


async def create_psy_test(psy_test_data: dict) -> PsyTest:
    async with get_async_db() as session:
        psy_test_item = PsyTest(**psy_test_data)
        session.add(psy_test_item)
        await session.commit()
        await session.refresh(psy_test_item)
        return psy_test_item


async def update_psy_test(psy_test_id: UUID, psy_test_data: dict) -> PsyTest | None:
    async with get_async_db() as session:
        stmt = (
            update(PsyTest)
            .where(PsyTest.id == psy_test_id)
            .values(**psy_test_data)
            .returning(PsyTest)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one_or_none()


async def delete_psy_test(psy_test_id: UUID) -> bool:
    async with get_async_db() as session:
        psy_test_item = await session.get(PsyTest, psy_test_id)
        if psy_test_item is None:
            return False

        await session.delete(psy_test_item)
        await session.commit()
        return True
