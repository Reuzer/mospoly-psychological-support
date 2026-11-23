from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from psychohelp.config.config import get_async_db
from psychohelp.models.psy_tests import PsyTest, PsyTestAttempt, PsyTestQuestion, PsyTestQuestionOption, QuestionType, TestType
from psychohelp.services.psy_test_exceptions import PsyTestNotFound, PsyTestStateConflict


async def get_psy_test_list(skip: int = 0, take: int = 100) -> list[tuple[PsyTest, int]]:
    questions_count = (
        select(func.count())
        .select_from(PsyTestQuestion)
        .where(PsyTestQuestion.test_id == PsyTest.id)
        .scalar_subquery()
    )
    async with get_async_db() as session:
        result = await session.execute(
            select(PsyTest, questions_count)
            .where(PsyTest.archived.is_(False))
            .order_by(PsyTest.created_at.desc())
            .offset(skip)
            .limit(take)
        )
        return [(test, count) for test, count in result]


async def get_psy_test_by_id(psy_test_id: UUID) -> PsyTest | None:
    async with get_async_db() as session:
        result = await session.execute(
            select(PsyTest).where(PsyTest.id == psy_test_id, PsyTest.archived.is_(False))
        )
        return result.scalar_one_or_none()


async def create_psy_test(psy_test_data: dict) -> PsyTest:
    data = psy_test_data.copy()
    questions = data.pop("questions", [])
    async with get_async_db() as session:
        async with session.begin():
            psy_test_item = PsyTest(**data)
            session.add(psy_test_item)
            await session.flush()
            session.add_all(_new_questions(psy_test_item.id, questions))
        return psy_test_item


async def require_medical_test(session: AsyncSession, test_id: UUID, *, lock: bool = False) -> PsyTest:
    query = select(PsyTest).where(PsyTest.id == test_id, PsyTest.type == TestType.MEDICAL)
    if lock:
        # FOR NO KEY UPDATE сериализует изменения теста и не блокирует проверку FK при завершении попытки.
        query = query.with_for_update(key_share=True)
    test = await session.scalar(query)
    if test is None:
        raise PsyTestNotFound("Медицинский тест не найден")
    return test


async def get_questions(session: AsyncSession, test_id: UUID) -> list[PsyTestQuestion]:
    return list(await session.scalars(
        select(PsyTestQuestion)
        .where(PsyTestQuestion.test_id == test_id)
        .options(selectinload(PsyTestQuestion.options))
        .order_by(PsyTestQuestion.position)
    ))


def _new_questions(test_id: UUID, questions: list[dict]) -> list[PsyTestQuestion]:
    return [
        PsyTestQuestion(
            test_id=test_id, position=position, text=question["text"],
            type=question.get("type", QuestionType.TEXT),
            options=[
                PsyTestQuestionOption(position=option_position, text=option["text"])
                for option_position, option in enumerate(question.get("options", []), start=1)
            ],
        )
        for position, question in enumerate(questions, start=1)
    ]


async def _require_editable_questions(session: AsyncSession, test_id: UUID) -> None:
    test = await require_medical_test(session, test_id, lock=True)
    if test.archived:
        raise PsyTestNotFound("Медицинский тест не найден")
    attempt_id = await session.scalar(
        select(PsyTestAttempt.id).where(PsyTestAttempt.test_id == test_id).limit(1)
    )
    if attempt_id is not None:
        raise PsyTestStateConflict("Вопросы теста зафиксированы после начала прохождения")


async def list_medical_test_questions(test_id: UUID) -> list[PsyTestQuestion]:
    async with get_async_db() as session:
        test = await require_medical_test(session, test_id)
        if test.archived:
            raise PsyTestNotFound("Медицинский тест не найден")
        return await get_questions(session, test_id)


async def update_medical_test_question_image(
    test_id: UUID, question_id: UUID, image: str | None,
) -> tuple[PsyTestQuestion, str | None]:
    async with get_async_db() as session:
        async with session.begin():
            await _require_editable_questions(session, test_id)
            question = await session.scalar(
                select(PsyTestQuestion)
                .where(PsyTestQuestion.id == question_id, PsyTestQuestion.test_id == test_id)
                .options(selectinload(PsyTestQuestion.options))
            )
            if question is None:
                raise PsyTestNotFound("Вопрос не найден")
            previous_image = question.image
            question.image = image
        return question, previous_image


async def update_psy_test_with_previous_image(
    psy_test_id: UUID, psy_test_data: dict,
) -> tuple[PsyTest | None, str | None]:
    if not psy_test_data:
        return await get_psy_test_by_id(psy_test_id), None

    async with get_async_db() as session:
        result = await session.execute(
            select(PsyTest)
            .where(PsyTest.id == psy_test_id, PsyTest.archived.is_(False))
            .with_for_update()
        )
        psy_test_item = result.scalar_one_or_none()
        if psy_test_item is None:
            return None, None
        if psy_test_data.get("type", psy_test_item.type) != psy_test_item.type:
            raise PsyTestStateConflict("Тип теста фиксируется при создании")
        if "url" in psy_test_data:
            if psy_test_item.type == TestType.MEDICAL and psy_test_data["url"] is not None:
                raise PsyTestStateConflict("Медицинский тест не содержит ссылку на внешний тест")
            if psy_test_item.type == TestType.ENTERTAINING and psy_test_data["url"] is None:
                raise PsyTestStateConflict("Развлекательному тесту нужна внешняя ссылка")
        previous_image = psy_test_item.image
        for field, value in psy_test_data.items():
            setattr(psy_test_item, field, value)
        await session.commit()
        return psy_test_item, previous_image


async def delete_psy_test_with_previous_image(psy_test_id: UUID) -> tuple[bool, str | None]:
    async with get_async_db() as session:
        result = await session.execute(
            select(PsyTest)
            .where(PsyTest.id == psy_test_id, PsyTest.archived.is_(False))
            .with_for_update()
        )
        psy_test_item = result.scalar_one_or_none()
        if psy_test_item is None:
            return False, None

        previous_image = psy_test_item.image
        if psy_test_item.type == TestType.MEDICAL:
            psy_test_item.archived = True
            psy_test_item.image = None
        else:
            await session.delete(psy_test_item)
        await session.commit()
        return True, previous_image
