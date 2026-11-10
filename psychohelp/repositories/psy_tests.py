from uuid import UUID

from sqlalchemy import select

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


async def update_psy_test_with_previous_image(
    psy_test_id: UUID, psy_test_data: dict,
) -> tuple[PsyTest | None, str | None]:
    if not psy_test_data:
        return await get_psy_test_by_id(psy_test_id), None

    async with get_async_db() as session:
        result = await session.execute(
            select(PsyTest)
            .where(PsyTest.id == psy_test_id)
            .with_for_update()
        )
        psy_test_item = result.scalar_one_or_none()
        if psy_test_item is None:
            return None, None
        previous_image = psy_test_item.image
        for field, value in psy_test_data.items():
            setattr(psy_test_item, field, value)
        await session.commit()
        return psy_test_item, previous_image


async def delete_psy_test_with_previous_image(psy_test_id: UUID) -> tuple[bool, str | None]:
    async with get_async_db() as session:
        result = await session.execute(
            select(PsyTest).where(PsyTest.id == psy_test_id).with_for_update()
        )
        psy_test_item = result.scalar_one_or_none()
        if psy_test_item is None:
            return False, None

        previous_image = psy_test_item.image
        await session.delete(psy_test_item)
        await session.commit()
        return True, previous_image
