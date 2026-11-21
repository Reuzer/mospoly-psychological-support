from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import selectinload

from psychohelp.config.config import get_async_db
from psychohelp.constants.rbac import RoleCode
from psychohelp.models.appointments import Appointment, AppointmentStatus
from psychohelp.models.assessment_completions import PsyTestCompletion, SurveyCompletion
from psychohelp.models.psy_tests import PsyTest, TestType
from psychohelp.models.psychologists import Psychologist
from psychohelp.models.roles import Role
from psychohelp.models.users import User
from psychohelp.services.medical_record_exceptions import (
    MedicalRecordNotFoundException,
    MedicalRecordNoteVersionConflict,
)


def _patient_query():
    # EXISTS не дублирует карточки пользователей с несколькими ролями.
    return select(User).options(selectinload(User.roles)).where(
        User.roles.any(Role.code == RoleCode.USER),
    )


async def get_medical_record_list() -> list[User]:
    async with get_async_db() as session:
        result = await session.execute(_patient_query())
        return list(result.scalars().all())


async def get_medical_record_by_user_id(user_id: UUID) -> dict | None:
    async with get_async_db() as session:
        result = await session.execute(_patient_query().where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            return None

        appointments_query = select(Appointment).options(
            selectinload(Appointment.patient),
            selectinload(Appointment.psychologist).selectinload(Psychologist.user),
        ).where(Appointment.patient_id == user_id)
        next_result = await session.execute(
            appointments_query.where(
                Appointment.status == AppointmentStatus.awaiting,
                Appointment.scheduled_time > datetime.now(timezone.utc),
            ).order_by(Appointment.scheduled_time, Appointment.id).limit(1)
        )
        completed_result = await session.execute(
            appointments_query.where(Appointment.status == AppointmentStatus.done)
        )

        # Независимые подзапросы исключают перемножение прохождений тестов и опросов.
        tests_count = select(func.count(distinct(PsyTestCompletion.test_id))).join(
            PsyTest, PsyTest.id == PsyTestCompletion.test_id,
        ).where(
            PsyTestCompletion.user_id == user_id,
            PsyTest.type == TestType.MEDICAL,
        ).scalar_subquery()
        surveys_count = select(func.count(distinct(SurveyCompletion.survey_id))).where(
            SurveyCompletion.user_id == user_id,
        ).scalar_subquery()
        counts = (await session.execute(select(tests_count, surveys_count))).one()

        return {
            "id": user.id,
            "user": user,
            "note": user.note,
            "note_version": user.note_version,
            "next_appointment": next_result.scalar_one_or_none(),
            "completed_appointments": list(completed_result.scalars().all()),
            "tests_count": counts[0],
            "surveys_count": counts[1],
        }


async def update_medical_record_note(
    user_id: UUID, note: str | None, note_version: int,
) -> User:
    async with get_async_db() as session:
        async with session.begin():
            result = await session.execute(
                _patient_query().where(User.id == user_id).with_for_update()
            )
            user = result.scalar_one_or_none()
            if user is None:
                raise MedicalRecordNotFoundException(user_id)
            # Проверяем версию после получения блокировки, чтобы не потерять чужую правку.
            if user.note_version != note_version:
                raise MedicalRecordNoteVersionConflict()
            user.note = note
            user.note_version += 1
        return user
