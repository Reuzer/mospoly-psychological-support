#ЫЫЫЫ
from psychohelp.models.appointments import (
    Appointment,
    AppointmentType,
    AppointmentStatus,
)
from sqlalchemy.orm import selectinload

from psychohelp.models.psychologists import Psychologist
from psychohelp.models.psychologist_statuses import PsychologistStatus, PsychologistStatusType
from psychohelp.models.appointment_reschedule_requests import (
    AppointmentRescheduleRequest,
    AppointmentRescheduleStatus,
)
from psychohelp.models.users import User
from psychohelp.config.config import get_async_db
from psychohelp.services.appointments import exceptions as exc

from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from uuid import UUID
from datetime import datetime, timezone


def _ensure_appointment_reassignable(appointment: Appointment) -> None:
    if appointment.status != AppointmentStatus.awaiting:
        raise ValueError("Нельзя переназначить завершенную или отмененную запись")
    scheduled_time = appointment.scheduled_time
    scheduled_time = (
        scheduled_time.astimezone(timezone.utc)
        if scheduled_time.tzinfo
        else scheduled_time.replace(tzinfo=timezone.utc)
    )
    if scheduled_time <= datetime.now(timezone.utc):
        raise ValueError("Нельзя переназначить запись, время которой уже наступило")


async def get_appointment_by_id(appointment_id: UUID, user_id: UUID) -> Appointment | None:
    """Получить запись по ID с проверкой прав доступа (пациент или психолог)"""
    async with get_async_db() as session:
        query = select(Appointment).options(
            selectinload(Appointment.patient),
            selectinload(Appointment.psychologist).selectinload(Psychologist.user)
        ).filter(
            Appointment.id == appointment_id,
            (
                (Appointment.patient_id == user_id) | 
                Appointment.psychologist.has(Psychologist.user_id == user_id)
            )
        )
        
        result = await session.execute(query)
        return result.scalar_one_or_none()


async def is_appointment_slot_available(
    psychologist_id: UUID,
    scheduled_time: datetime,
    exclude_appointment_id: UUID | None = None,
) -> bool:
    async with get_async_db() as session:
        query = select(Appointment.id).where(
            Appointment.psychologist_id == psychologist_id,
            Appointment.scheduled_time == scheduled_time,
            Appointment.status == AppointmentStatus.awaiting,
        )
        if exclude_appointment_id is not None:
            query = query.where(Appointment.id != exclude_appointment_id)

        result = await session.execute(query)
        return result.scalar_one_or_none() is None


async def update_emergency_contact(
    appointment_id: UUID, user_id: UUID, emergency_contact: str | None,
) -> Appointment:
    async with get_async_db() as session:
        result = await session.execute(
            select(Appointment)
            .options(
                selectinload(Appointment.patient),
                selectinload(Appointment.psychologist).selectinload(Psychologist.user),
            )
            .where(Appointment.id == appointment_id)
            .with_for_update()
        )
        appointment = result.scalar_one_or_none()
        if appointment is None or (
            appointment.patient_id != user_id
            and appointment.psychologist.user_id != user_id
        ):
            raise exc.AppointmentNotFoundException(appointment_id)
        if appointment.status != AppointmentStatus.awaiting:
            raise exc.AppointmentNotActiveException(appointment_id)

        appointment.emergency_contact = emergency_contact
        appointment.last_change_time = datetime.now(timezone.utc)
        await session.commit()
        return appointment


async def create_appointment(
    patient_id: UUID,
    psychologist_id: UUID,
    type: AppointmentType,
    duration: int,
    reason: str | None,
    status: AppointmentStatus,
    scheduled_time: datetime,
    remind_time: datetime | None,
    last_change_time: datetime,
    venue: str,
    comment: str | None = None,
) -> Appointment:
    async with get_async_db() as session:
        new_appointment = Appointment(
            patient_id=patient_id,
            psychologist_id=psychologist_id,
            type=type,
            duration=duration,
            reason=reason,
            status=status,
            scheduled_time=scheduled_time,
            remind_time=remind_time,
            last_change_time=last_change_time,
            venue=venue,
            comment=comment,
        )

        try:
            session.add(new_appointment)
            await session.commit()
            await session.refresh(new_appointment)
        except IntegrityError:
            await session.rollback()
            raise

        return new_appointment


async def cancel_appointment_by_id(
    appointment_id: UUID,
    current_user_id: UUID,
    cancel_reason: str,
    is_emergency: bool = False,
) -> Appointment:
    async with get_async_db() as session:
        # Благодаря selectinload(Appointment.psychologist) у нас есть доступ к объекту психолога
        query = select(Appointment).options(
            selectinload(Appointment.patient),
            selectinload(Appointment.psychologist).selectinload(Psychologist.user)
        ).filter(Appointment.id == appointment_id).with_for_update()
        
        result = await session.execute(query)
        appointment = result.scalar_one_or_none()

        if appointment is None:
            raise ValueError("Встреча не найдена")

        is_patient = appointment.patient_id == current_user_id
        is_psychologist = appointment.psychologist.user_id == current_user_id

        if not is_patient and not is_psychologist:
            raise PermissionError("Только пациент или назначенный психолог может отменить запись")

        if is_psychologist and not is_emergency:
            raise PermissionError("Психолог может отменить запись только при ЧС")

        if appointment.status in (AppointmentStatus.done, AppointmentStatus.cancelled):
            raise ValueError("Завершенную или отмененную запись нельзя отменить повторно")

        appointment.status = AppointmentStatus.cancelled
        appointment.cancel_reason = cancel_reason
        appointment.cancelled_by = "patient" if is_patient else "psychologist"
        appointment.emergency_cancellation = is_psychologist
        appointment.last_change_time = datetime.now(timezone.utc)

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise

        return appointment


async def get_appointments_by_user_id(user_id: UUID) -> list[Appointment]:
    async with get_async_db() as session:
        query = (
            select(Appointment)
            .options( # Добавили selectinload
                selectinload(Appointment.patient),
                selectinload(Appointment.psychologist).selectinload(Psychologist.user)
            )
            .outerjoin(Psychologist, Appointment.psychologist_id == Psychologist.id)
            .filter(
                (Appointment.patient_id == user_id) | 
                (Psychologist.user_id == user_id)
            )
        )
        
        result = await session.execute(query)
        return list(result.scalars().all())


async def reassign_appointment_to_psychologist(
    appointment_id: UUID,
    psychologist_user_id: UUID,
) -> Appointment:
    """Атомарно сменить психолога записи и закрыть ожидающие запросы переноса."""
    async with get_async_db() as session:
        async with session.begin():
            appointment_result = await session.execute(
                select(Appointment)
                .options(
                    selectinload(Appointment.patient),
                    selectinload(Appointment.psychologist).selectinload(Psychologist.user),
                )
                .where(Appointment.id == appointment_id)
                .with_for_update()
            )
            appointment = appointment_result.scalar_one_or_none()
            if appointment is None:
                raise exc.AppointmentNotFoundException(appointment_id)
            _ensure_appointment_reassignable(appointment)

            psychologist_result = await session.execute(
                select(Psychologist)
                .options(selectinload(Psychologist.user))
                .where(Psychologist.user_id == psychologist_user_id)
                .with_for_update()
            )
            psychologist = psychologist_result.scalar_one_or_none()
            if psychologist is None:
                raise PermissionError("Для переназначения необходим профиль психолога")
            if appointment.psychologist_id == psychologist.id:
                _ensure_appointment_reassignable(appointment)
                return appointment

            unavailable_result = await session.execute(
                select(PsychologistStatus)
                .where(
                    PsychologistStatus.pid == psychologist_user_id,
                    PsychologistStatus.status.in_(
                        (PsychologistStatusType.sick, PsychologistStatusType.vacation)
                    ),
                    PsychologistStatus.start_date <= appointment.scheduled_time,
                    PsychologistStatus.end_date >= appointment.scheduled_time,
                )
                .with_for_update()
            )
            if unavailable_result.scalars().first() is not None:
                raise exc.PsychologistUnavailableException(
                    psychologist.id, appointment.scheduled_time
                )

            # Блокировка профиля сериализует переназначения на одного психолога.
            # Другие встречи только читаем: их блокировка может вызвать дедлок
            # с переназначением, уже захватившим свою встречу и ожидающим профиль.
            busy_result = await session.execute(
                select(Appointment.id)
                .where(
                    Appointment.psychologist_id == psychologist.id,
                    Appointment.status == AppointmentStatus.awaiting,
                    Appointment.scheduled_time == appointment.scheduled_time,
                    Appointment.id != appointment_id,
                )
                .limit(1)
            )
            if busy_result.scalars().first() is not None:
                raise exc.PsychologistUnavailableException(
                    psychologist.id, appointment.scheduled_time
                )

            pending_result = await session.execute(
                select(AppointmentRescheduleRequest)
                .where(
                    AppointmentRescheduleRequest.appointment_id == appointment_id,
                    AppointmentRescheduleRequest.status == AppointmentRescheduleStatus.pending,
                )
                .with_for_update()
            )
            pending_requests = list(pending_result.scalars().all())

            # Ожидание блокировок могло занять время до начала встречи.
            _ensure_appointment_reassignable(appointment)
            now = datetime.now(timezone.utc)
            appointment.psychologist_id = psychologist.id
            appointment.psychologist = psychologist
            appointment.last_change_time = now
            for pending_request in pending_requests:
                pending_request.status = AppointmentRescheduleStatus.rejected
                pending_request.rejection_comment = "Запись переназначена другому психологу"
                pending_request.responded_at = now

            await session.flush()
            refreshed_result = await session.execute(
                select(Appointment)
                .options(
                    selectinload(Appointment.patient),
                    selectinload(Appointment.psychologist).selectinload(Psychologist.user),
                )
                .where(Appointment.id == appointment_id)
                .execution_options(populate_existing=True)
            )
            return refreshed_result.scalar_one()


async def complete_appointment_by_psychologist(
        appointment_id: UUID,
        psychologist_id: UUID,
        patient_comment: str | None = None,
        psychologist_comment: str | None = None) -> Appointment:
    async with get_async_db() as session:
        # Добавили selectinload для всех нужных связей
        query = select(Appointment).options(
            selectinload(Appointment.patient),
            selectinload(Appointment.psychologist).selectinload(Psychologist.user)
        ).filter(Appointment.id == appointment_id).with_for_update()
        
        result = await session.execute(query)
        appointment = result.scalar_one_or_none()

        if appointment is None:
            raise ValueError("Встреча не найдена")
        if appointment.psychologist.user_id != psychologist_id:
            raise PermissionError("Только назначенный психолог может завершить прием")
        if appointment.status in (AppointmentStatus.done, AppointmentStatus.cancelled):
            raise ValueError("Нельзя завершить эту встречу (она уже завершена или отменена)")

        appointment.status = AppointmentStatus.done
        appointment.conclusion = patient_comment
        appointment.psychologist_comment = psychologist_comment
        appointment.last_change_time = datetime.now(timezone.utc)

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise

        return appointment
