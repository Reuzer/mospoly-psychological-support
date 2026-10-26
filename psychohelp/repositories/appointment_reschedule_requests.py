from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from psychohelp.config.config import get_async_db
from psychohelp.models.appointment_reschedule_requests import (
    AppointmentRescheduleRequest,
    AppointmentRescheduleStatus,
)
from psychohelp.models.appointments import Appointment, AppointmentStatus
from psychohelp.models.psychologists import Psychologist


def _ensure_appointment_open(appointment: Appointment) -> None:
    if appointment.status in (AppointmentStatus.done, AppointmentStatus.cancelled):
        raise ValueError("Нельзя перенести завершенную или отмененную запись")


async def create_reschedule_request(
    appointment_id: UUID,
    psychologist_user_id: UUID,
    scheduled_time: datetime,
    remind_time: datetime | None,
    venue: str | None,
    comment: str | None,
) -> AppointmentRescheduleRequest:
    async with get_async_db() as session:
        query = (
            select(Appointment)
            .options(selectinload(Appointment.psychologist))
            .where(Appointment.id == appointment_id)
        )
        result = await session.execute(query)
        appointment = result.scalar_one_or_none()

        if appointment is None:
            raise ValueError("Встреча не найдена")
        if appointment.psychologist.user_id != psychologist_user_id:
            raise PermissionError("Только назначенный психолог может запросить перенос")

        _ensure_appointment_open(appointment)

        pending_result = await session.execute(
            select(AppointmentRescheduleRequest).where(
                AppointmentRescheduleRequest.appointment_id == appointment_id,
                AppointmentRescheduleRequest.status == AppointmentRescheduleStatus.pending,
            )
        )
        if pending_result.scalar_one_or_none() is not None:
            raise ValueError("По этой записи уже запрошен перенос")

        reschedule_request = AppointmentRescheduleRequest(
            appointment_id=appointment_id,
            requested_by_user_id=psychologist_user_id,
            old_scheduled_time=appointment.scheduled_time,
            old_remind_time=appointment.remind_time,
            old_venue=appointment.venue,
            old_comment=appointment.comment,
            requested_scheduled_time=scheduled_time,
            requested_remind_time=remind_time,
            requested_venue=venue,
            requested_comment=comment,
        )

        try:
            session.add(reschedule_request)
            await session.commit()
            await session.refresh(reschedule_request)
        except IntegrityError:
            await session.rollback()
            raise ValueError("По этой записи уже запрошен перенос")

        return reschedule_request


async def get_reschedule_requests_by_appointment(
    appointment_id: UUID,
    user_id: UUID,
) -> list[AppointmentRescheduleRequest]:
    async with get_async_db() as session:
        appointment_result = await session.execute(
            select(Appointment)
            .outerjoin(Psychologist, Appointment.psychologist_id == Psychologist.id)
            .where(
                Appointment.id == appointment_id,
                (
                    (Appointment.patient_id == user_id)
                    | (Psychologist.user_id == user_id)
                ),
            )
        )
        if appointment_result.scalar_one_or_none() is None:
            raise ValueError("Встреча не найдена")

        result = await session.execute(
            select(AppointmentRescheduleRequest)
            .where(AppointmentRescheduleRequest.appointment_id == appointment_id)
            .order_by(AppointmentRescheduleRequest.created_at.desc())
        )
        return list(result.scalars().all())


async def confirm_reschedule_request(
    request_id: UUID,
    patient_user_id: UUID,
) -> AppointmentRescheduleRequest:
    async with get_async_db() as session:
        query = (
            select(AppointmentRescheduleRequest)
            .options(selectinload(AppointmentRescheduleRequest.appointment))
            .where(AppointmentRescheduleRequest.id == request_id)
            .with_for_update()
        )
        result = await session.execute(query)
        reschedule_request = result.scalar_one_or_none()

        if reschedule_request is None:
            raise ValueError("Запрос переноса не найден")
        if reschedule_request.status != AppointmentRescheduleStatus.pending:
            raise ValueError("Запрос переноса уже обработан")

        appointment = reschedule_request.appointment
        if appointment.patient_id != patient_user_id:
            raise PermissionError("Только пациент может подтвердить перенос")

        _ensure_appointment_open(appointment)

        now = datetime.now(timezone.utc)
        appointment.scheduled_time = reschedule_request.requested_scheduled_time
        appointment.remind_time = reschedule_request.requested_remind_time
        if reschedule_request.requested_venue is not None:
            appointment.venue = reschedule_request.requested_venue
        if reschedule_request.requested_comment is not None:
            appointment.comment = reschedule_request.requested_comment
        appointment.last_change_time = now

        reschedule_request.status = AppointmentRescheduleStatus.confirmed
        reschedule_request.responded_at = now

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise
        await session.refresh(reschedule_request)
        return reschedule_request


async def cancel_reschedule_request(
    request_id: UUID,
    patient_user_id: UUID,
    rejection_comment: str,
) -> AppointmentRescheduleRequest:
    async with get_async_db() as session:
        query = (
            select(AppointmentRescheduleRequest)
            .options(selectinload(AppointmentRescheduleRequest.appointment))
            .where(AppointmentRescheduleRequest.id == request_id)
            .with_for_update()
        )
        result = await session.execute(query)
        reschedule_request = result.scalar_one_or_none()

        if reschedule_request is None:
            raise ValueError("Запрос переноса не найден")
        if reschedule_request.status != AppointmentRescheduleStatus.pending:
            raise ValueError("Запрос переноса уже обработан")

        appointment = reschedule_request.appointment
        if appointment.patient_id != patient_user_id:
            raise PermissionError("Только пациент может отклонить перенос")

        _ensure_appointment_open(appointment)

        now = datetime.now(timezone.utc)
        appointment.status = AppointmentStatus.cancelled
        appointment.cancel_reason = rejection_comment
        appointment.cancelled_by = "patient"
        appointment.emergency_cancellation = False
        appointment.last_change_time = now

        reschedule_request.status = AppointmentRescheduleStatus.rejected
        reschedule_request.rejection_comment = rejection_comment
        reschedule_request.responded_at = now

        await session.commit()
        await session.refresh(reschedule_request)
        return reschedule_request


async def reject_reschedule_request(
    request_id: UUID,
    patient_user_id: UUID,
    rejection_comment: str,
) -> AppointmentRescheduleRequest:
    """Backward-compatible alias: rejecting a transfer cancels the appointment."""
    return await cancel_reschedule_request(
        request_id=request_id,
        patient_user_id=patient_user_id,
        rejection_comment=rejection_comment,
    )
