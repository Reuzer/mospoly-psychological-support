from psychohelp.models.appointments import (
    Appointment,
    AppointmentType,
    AppointmentStatus,
)
from sqlalchemy.orm import selectinload

from psychohelp.models.psychologists import Psychologist
from psychohelp.models.users import User
from psychohelp.config.config import get_async_db
from psychohelp.services.appointments.exceptions import (
    AppointmentNotActiveException,
    AppointmentNotFoundException,
)

from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from uuid import UUID
from datetime import datetime, timezone


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
            raise AppointmentNotFoundException(appointment_id)
        if appointment.status != AppointmentStatus.awaiting:
            raise AppointmentNotActiveException(appointment_id)

        appointment.emergency_contact = emergency_contact
        appointment.last_change_time = datetime.now(timezone.utc)
        await session.commit()
        return appointment


async def create_appointment(
    patient_id: UUID,
    psychologist_id: UUID,
    type: AppointmentType,
    reason: str | None,
    status: AppointmentStatus,
    scheduled_time: datetime,
    remind_time: datetime | None,
    last_change_time: datetime,
    venue: str,
    application_id: UUID | None = None,
    comment: str | None = None,
) -> Appointment:
    # Убрали передачу имен из параметров
    async with get_async_db() as session:
        new_appointment = Appointment(
            patient_id=patient_id,
            psychologist_id=psychologist_id,
            application_id=application_id,
            type=type,
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


async def cancel_appointment_by_id(appointment_id: UUID, current_user_id: UUID, cancel_reason: str) -> Appointment:
    async with get_async_db() as session:
        # Благодаря selectinload(Appointment.psychologist) у нас есть доступ к объекту психолога
        query = select(Appointment).options(
            selectinload(Appointment.patient),
            selectinload(Appointment.psychologist).selectinload(Psychologist.user)
        ).filter(Appointment.id == appointment_id)
        
        result = await session.execute(query)
        appointment = result.scalar_one_or_none()

        if appointment is None:
            raise ValueError("Встреча не найдена")

        if appointment.patient_id != current_user_id and appointment.psychologist.user_id != current_user_id:
            raise ValueError("Только пациент или психолог может отменить свою запись")

        if appointment.status == AppointmentStatus.cancelled:
            raise ValueError("Встреча уже отменена")

        appointment.status = AppointmentStatus.cancelled
        appointment.cancel_reason = cancel_reason
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


async def complete_appointment_by_psychologist(
        appointment_id: UUID,
        psychologist_id: UUID,
        patient_comment: str,
        psychologist_comment: str | None = None) -> Appointment:
    async with get_async_db() as session:
        # Добавили selectinload для всех нужных связей
        query = select(Appointment).options(
            selectinload(Appointment.patient),
            selectinload(Appointment.psychologist).selectinload(Psychologist.user)
        ).filter(Appointment.id == appointment_id)
        
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
