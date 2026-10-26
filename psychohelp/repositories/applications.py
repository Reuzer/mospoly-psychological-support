from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.orm import selectinload

from psychohelp.config.config import get_async_db
from psychohelp.models.applications import Application, ApplicationStatus
from psychohelp.models.appointments import (
    Appointment,
    AppointmentStatus,
    AppointmentType,
)
from psychohelp.models.psychologists import Psychologist
from psychohelp.models.psychologist_statuses import (
    PsychologistStatus,
    PsychologistStatusType,
)
from psychohelp.services.applications.exceptions import (
    AccessDeniedError,
    ApplicationNotFoundError,
    ConflictError,
    InvalidStatusTransitionError,
    ValidationError,
)


async def create_application(application_data: dict) -> Application:
    async with get_async_db() as session:
        application = Application(**application_data)
        session.add(application)
        await session.commit()
        await session.refresh(application)
        return application


async def get_application_by_id(
    application_id: UUID,
) -> Application | None:
    async with get_async_db() as session:
        result = await session.execute(
            select(Application)
            .options(
                selectinload(Application.user),
                selectinload(Application.assigned_to_user),
                selectinload(
                    Application.appointment
                ).selectinload(Appointment.patient),
                selectinload(
                    Application.psychologist
                ).selectinload(Psychologist.user),
            )
            .where(Application.id == application_id)
        )
        return result.scalar_one_or_none()


async def get_applications(
    skip: int = 0,
    limit: int = 100,
    status: ApplicationStatus | None = None,
    assigned_to: UUID | None = None,
    user_id: UUID | None = None,
    sort_by: str = "created_at",
    sort_desc: bool = True,
) -> list[Application]:
    async with get_async_db() as session:
        query = select(Application).options(
            selectinload(Application.user),
            selectinload(Application.assigned_to_user),
            selectinload(
                Application.appointment
            ).selectinload(Appointment.patient),
            selectinload(
                Application.psychologist
            ).selectinload(Psychologist.user),
        )

        filters = []

        if status:
            filters.append(Application.status == status.value)

        if assigned_to:
            filters.append(
                Application.assigned_to == assigned_to
            )

        if user_id:
            filters.append(Application.user_id == user_id)

        if filters:
            query = query.where(and_(*filters))

        if sort_by:
            column = getattr(Application, sort_by)
            order = column.desc() if sort_desc else column.asc()
            query = query.order_by(order)

        query = query.offset(skip).limit(limit)

        result = await session.execute(query)

        return list(result.scalars().all())


async def update_application_with_version(
    application_id: UUID,
    expected_version: int,
    update_data: dict,
) -> Application | None:
    """
    Обновление с оптимистичной блокировкой.

    Возвращает None при конфликте версий.
    """

    async with get_async_db() as session:
        stmt = (
            update(Application)
            .where(
                Application.id == application_id,
                Application.version == expected_version,
            )
            .values(
                **update_data,
                version=Application.version + 1,
            )
            .returning(Application)
        )

        result = await session.execute(stmt)
        await session.commit()

        return result.scalar_one_or_none()


async def update_application(
    application_id: UUID,
    update_data: dict,
) -> Application | None:
    async with get_async_db() as session:
        stmt = (
            update(Application)
            .where(Application.id == application_id)
            .values(**update_data)
            .returning(Application)
        )

        result = await session.execute(stmt)
        await session.commit()

        return result.scalar_one_or_none()


async def confirm_application_and_create_appointment(
    application_id: UUID,
    actor_id: UUID,
    expected_version: int,
) -> Application:
    """
    Атомарно подтверждает актуальную версию заявки
    и создает Appointment из серверных данных заявки.
    """

    async with get_async_db() as session:
        async with session.begin():
            application_result = await session.execute(
                select(Application)
                .where(Application.id == application_id)
                .with_for_update()
            )

            application = (
                application_result.scalar_one_or_none()
            )

            if application is None:
                raise ApplicationNotFoundError()

            if application.user_id != actor_id:
                raise AccessDeniedError(
                    "Вы можете подтверждать только свои заявки"
                )

            if (
                application.status
                == ApplicationStatus.COMPLETED.value
            ):
                raise ConflictError(
                    "Заявка уже подтверждена"
                )

            if (
                application.status
                != ApplicationStatus.AWAITING_USER_CONFIRMATION.value
            ):
                raise InvalidStatusTransitionError(
                    "Невозможно подтвердить заявку "
                    f"из статуса {application.status}"
                )

            if application.version != expected_version:
                raise ConflictError(
                    "Условия заявки были изменены. "
                    "Обновите заявку и подтвердите новую версию"
                )

            if application.psychologist_id is None:
                raise ValidationError(
                    "Для заявки не назначен психолог"
                )

            if application.scheduled_at is None:
                raise ValidationError(
                    "Для заявки не указаны дата и время консультации"
                )

            scheduled_at = application.scheduled_at

            scheduled_at = (
                scheduled_at.astimezone(timezone.utc)
                if scheduled_at.tzinfo
                else scheduled_at.replace(
                    tzinfo=timezone.utc
                )
            )

            now = datetime.now(timezone.utc)

            if scheduled_at <= now:
                raise ValidationError(
                    "Дата и время встречи не могут быть в прошлом"
                )

            psychologist_result = await session.execute(
                select(Psychologist)
                .where(
                    Psychologist.id
                    == application.psychologist_id
                )
                .with_for_update()
            )

            psychologist = (
                psychologist_result.scalar_one_or_none()
            )

            if psychologist is None:
                raise ValidationError(
                    "Назначенный психолог не найден"
                )

            unavailable_result = await session.execute(
                select(PsychologistStatus)
                .where(
                    PsychologistStatus.pid
                    == psychologist.user_id,
                    PsychologistStatus.status.in_(
                        (
                            PsychologistStatusType.sick,
                            PsychologistStatusType.vacation,
                        )
                    ),
                    PsychologistStatus.start_date
                    <= scheduled_at,
                    PsychologistStatus.end_date
                    >= scheduled_at,
                )
                .with_for_update()
            )

            if (
                unavailable_result.scalars().first()
                is not None
            ):
                raise ConflictError(
                    "Назначенный психолог недоступен "
                    "в указанное время"
                )

            if application.meeting_type == "offline":
                appointment_type = (
                    AppointmentType.Offline
                )

                venue = (
                    application.location_address or ""
                ).strip()

                if not venue:
                    raise ValidationError(
                        "Для очной встречи не указан адрес"
                    )

            elif application.meeting_type == "online":
                appointment_type = (
                    AppointmentType.Online
                )

                venue = (
                    application.meeting_url or ""
                ).strip()

                if not venue:
                    raise ValidationError(
                        "Для онлайн-встречи не указана ссылка"
                    )

            else:
                raise ValidationError(
                    "Для заявки не указан формат встречи"
                )

            if len(venue) > 128:
                raise ValidationError(
                    "Место встречи или ссылка "
                    "не могут быть длиннее 128 символов"
                )

            # Проверка до блокировки психолога могла устареть за время ожидания.
            now = datetime.now(timezone.utc)
            if scheduled_at <= now:
                raise ValidationError(
                    "Дата и время встречи не могут быть в прошлом"
                )

            appointment = Appointment(
                patient_id=application.user_id,
                psychologist_id=(
                    application.psychologist_id
                ),
                application_id=application.id,
                type=appointment_type,
                reason=None,
                status=AppointmentStatus.awaiting,
                scheduled_time=scheduled_at,
                remind_time=None,
                last_change_time=now,
                venue=venue,
                comment=None,
            )

            session.add(appointment)

            await session.flush()

            application.appointment_id = appointment.id
            application.status = (
                ApplicationStatus.COMPLETED.value
            )
            application.completed_at = now
            application.updated_at = now
            application.version += 1

            await session.flush()

            refreshed_result = await session.execute(
                select(Application)
                .options(
                    selectinload(Application.user),
                    selectinload(
                        Application.assigned_to_user
                    ),
                    selectinload(
                        Application.appointment
                    ).selectinload(
                        Appointment.patient
                    ),
                    selectinload(
                        Application.psychologist
                    ).selectinload(
                        Psychologist.user
                    ),
                )
                .where(
                    Application.id == application_id
                )
                .execution_options(
                    populate_existing=True
                )
            )

            return refreshed_result.scalar_one()


async def delete_application(
    application_id: UUID,
) -> bool:
    async with get_async_db() as session:
        application = await session.get(
            Application,
            application_id,
        )

        if application:
            await session.delete(application)
            await session.commit()
            return True

        return False
