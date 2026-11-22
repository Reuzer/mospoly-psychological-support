from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from psychohelp.config.config import get_async_db
from psychohelp.models.assessment_completions import PsyTestCompletion
from psychohelp.models.psy_tests import PsyTest, PsyTestAnswer, PsyTestAttempt, PsyTestQuestion, QuestionType
from psychohelp.repositories.psy_tests import get_questions, require_medical_test
from psychohelp.services.psy_test_exceptions import PsyTestInvalidAnswer, PsyTestNotFound, PsyTestStateConflict


def _attempt_query(user_id: UUID):
    return (
        select(PsyTestAttempt, PsyTest.title)
        .join(PsyTest, PsyTest.id == PsyTestAttempt.test_id)
        .where(PsyTestAttempt.user_id == user_id)
    )


def _summary(attempt: PsyTestAttempt, title: str) -> dict:
    return {
        "id": attempt.id,
        "user_id": attempt.user_id,
        "test_id": attempt.test_id,
        "test_title": title,
        "started_at": attempt.started_at,
        "completed_at": attempt.completed_at,
    }


async def _answers(session: AsyncSession, attempt_id: UUID) -> dict[UUID, PsyTestAnswer]:
    answers = await session.scalars(
        select(PsyTestAnswer).where(PsyTestAnswer.attempt_id == attempt_id)
    )
    return {answer.question_id: answer for answer in answers}


def _next_question(
    questions: list[PsyTestQuestion], answers: dict[UUID, PsyTestAnswer],
) -> PsyTestQuestion | None:
    return next((question for question in questions if question.id not in answers), None)


def _saved_answer(question: PsyTestQuestion, saved: PsyTestAnswer) -> dict:
    value = {"answer": saved.answer} if saved.option_ids is None else {"option_ids": saved.option_ids}
    return {"question": question, "answered_at": saved.answered_at, **value}


def _progress(
    attempt: PsyTestAttempt, title: str, questions: list[PsyTestQuestion],
    answers: dict[UUID, PsyTestAnswer],
) -> dict:
    return {
        **_summary(attempt, title),
        "answers": [
            _saved_answer(question, answers[question.id])
            for question in questions if question.id in answers
        ],
        "next_question": None if attempt.completed_at else _next_question(questions, answers),
    }


async def start_or_resume_attempt(test_id: UUID, user_id: UUID) -> dict:
    async with get_async_db() as session:
        async with session.begin():
            # Эта же блокировка защищает список вопросов от изменений при старте.
            test = await require_medical_test(session, test_id, lock=True)
            attempt = await session.scalar(
                select(PsyTestAttempt)
                .where(
                    PsyTestAttempt.test_id == test_id, PsyTestAttempt.user_id == user_id,
                    PsyTestAttempt.completed_at.is_(None),
                )
                .with_for_update(read=True)
            )
            if attempt is None and test.archived:
                raise PsyTestNotFound("Медицинский тест не найден")
            questions = await get_questions(session, test_id)
            if not questions:
                raise PsyTestStateConflict("В медицинском тесте пока нет вопросов")
            if attempt is None:
                attempt = PsyTestAttempt(test_id=test_id, user_id=user_id)
                session.add(attempt)
                await session.flush()
                return _progress(attempt, test.title, questions, {})
            return _progress(attempt, test.title, questions, await _answers(session, attempt.id))


async def get_attempt(user_id: UUID, attempt_id: UUID, *, test_id: UUID | None = None) -> dict:
    async with get_async_db() as session:
        query = _attempt_query(user_id).where(PsyTestAttempt.id == attempt_id)
        if test_id is not None:
            query = query.where(PsyTestAttempt.test_id == test_id)
        # Ответы и статус прочитываются в одном состоянии даже при параллельной записи.
        result = (await session.execute(query.with_for_update(read=True, of=PsyTestAttempt))).one_or_none()
        if result is None:
            raise PsyTestNotFound("Прохождение теста не найдено")
        attempt, title = result
        questions = await get_questions(session, attempt.test_id)
        return _progress(attempt, title, questions, await _answers(session, attempt.id))


async def list_attempts_by_user(user_id: UUID, skip: int, take: int) -> list[dict]:
    async with get_async_db() as session:
        result = await session.execute(
            _attempt_query(user_id)
            .order_by(PsyTestAttempt.started_at.desc(), PsyTestAttempt.id.desc())
            .offset(skip)
            .limit(take)
        )
        return [_summary(attempt, title) for attempt, title in result]


def _validate_answer_options(
    question: PsyTestQuestion, answer: str | None, option_ids: list[UUID] | None,
) -> list[UUID] | None:
    if question.type == QuestionType.TEXT:
        if answer is None or option_ids is not None:
            raise PsyTestInvalidAnswer("Для текстового вопроса передайте текст ответа")
        return None
    if answer is not None or not option_ids:
        raise PsyTestInvalidAnswer("Передайте UUID выбранных вариантов")
    if question.type == QuestionType.SINGLE_CHOICE and len(option_ids) != 1:
        raise PsyTestInvalidAnswer("Выберите ровно один вариант ответа")

    selected_ids = set(option_ids)
    # Храним выбранные UUID в порядке вариантов вопроса, чтобы повтор запроса был идемпотентным.
    selected = [option.id for option in question.options if option.id in selected_ids]
    if len(selected) != len(option_ids):
        raise PsyTestInvalidAnswer("Передайте уникальные варианты этого вопроса")
    return selected


async def save_answer(
    test_id: UUID, attempt_id: UUID, user_id: UUID, question_id: UUID,
    *, answer: str | None = None, option_ids: list[UUID] | None = None,
) -> dict:
    async with get_async_db() as session:
        async with session.begin():
            result = (await session.execute(
                _attempt_query(user_id)
                .where(PsyTestAttempt.id == attempt_id, PsyTestAttempt.test_id == test_id)
                .with_for_update(of=PsyTestAttempt)
            )).one_or_none()
            if result is None:
                raise PsyTestNotFound("Прохождение теста не найдено")
            attempt, title = result
            questions = await get_questions(session, test_id)
            answers = await _answers(session, attempt_id)
            existing = answers.get(question_id)
            if existing is None:
                if attempt.completed_at is not None:
                    raise PsyTestStateConflict("Тест уже завершён")
                question = _next_question(questions, answers)
                if question is None or question.id != question_id:
                    raise PsyTestStateConflict("Ответьте на следующий вопрос по порядку")
            else:
                question = next(item for item in questions if item.id == question_id)
            selected = _validate_answer_options(question, answer, option_ids)

            if existing is not None:
                if existing.answer != answer or existing.option_ids != selected:
                    raise PsyTestStateConflict("Ответ на этот вопрос уже сохранён")
                return _progress(attempt, title, questions, answers)

            now = datetime.now(timezone.utc)
            saved = PsyTestAnswer(
                attempt_id=attempt_id, question_id=question_id,
                answer=answer, option_ids=selected, answered_at=now,
            )
            session.add(saved)
            answers[question_id] = saved
            if len(answers) == len(questions):
                attempt.completed_at = now
                session.add(PsyTestCompletion(
                    id=attempt_id, user_id=user_id, test_id=test_id, completed_at=now,
                ))
            return _progress(attempt, title, questions, answers)
