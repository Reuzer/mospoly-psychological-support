from datetime import datetime, timezone
from uuid import UUID

from psychohelp.repositories import get_user_id_from_token
from psychohelp.repositories import appointment_reschedule_requests as reschedule_repo
from psychohelp.repositories.appointments import (
    get_appointment_by_id as repo_get_appointment_by_id,
    create_appointment as repo_create_appointment,
    cancel_appointment_by_id as repo_cancel_appointment_by_id,
    get_appointments_by_user_id as repo_get_appointments_by_user_id,
)
from psychohelp.repositories.applications import get_application_by_id
from psychohelp.repositories.psychologists.psychologists import (
    get_psychologist_by_id,
    get_psychologist_by_user_id,
    check_psychologist_availability
)
from psychohelp.repositories.users import get_user_by_id
from psychohelp.models.appointments import Appointment, AppointmentType, AppointmentStatus
from psychohelp.services.appointments import exceptions as exc
from psychohelp.services.applications.applications import confirm_application
from psychohelp.repositories.appointments import cancel_appointment_by_id as repo_cancel


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _validate_appointment_time(
    scheduled_time: datetime,
    remind_time: datetime | None,
) -> tuple[datetime, datetime | None]:
    now = datetime.now(timezone.utc)
    scheduled_time_utc = _as_utc(scheduled_time)
    if scheduled_time_utc <= now:
        raise exc.InvalidScheduledTimeException(scheduled_time)

    remind_time_utc = None
    if remind_time is not None:
        remind_time_utc = _as_utc(remind_time)
        if remind_time_utc <= now:
            raise exc.InvalidRemindTimeException(
                remind_time,
                "время напоминания не может быть в прошлом",
            )
        if remind_time_utc >= scheduled_time_utc:
            raise exc.InvalidRemindTimeException(
                remind_time,
                "время напоминания должно быть раньше времени встречи",
            )

    return scheduled_time_utc, remind_time_utc


async def get_appointment_by_id(appointment_id: UUID, user_id: UUID) -> Appointment | None:
    return await repo_get_appointment_by_id(appointment_id, user_id)


async def create_appointment(
    patient_id: UUID,
    psychologist_id: UUID,
    type: AppointmentType,
    scheduled_time: datetime,
    reason: str | None = None,
    remind_time: datetime | None = None,
    venue: str | None = None,
    comment: str | None = None,
    application_id: UUID | None = None,
) -> Appointment:
    now = datetime.now(timezone.utc)
    status = AppointmentStatus.awaiting

    scheduled_time_utc, remind_time_utc = _validate_appointment_time(scheduled_time, remind_time)

    patient = await get_user_by_id(patient_id)
    if patient is None:
        raise exc.PatientNotFoundException(patient_id)

    # Проверка существования заявки
    if application_id:
        application = await get_application_by_id(application_id)
        if application is None:
            raise exc.ApplicationNotFoundException(application_id)

    psychologist = await get_psychologist_by_id(psychologist_id)
    if psychologist is None:
        psychologist = await get_psychologist_by_user_id(psychologist_id)
    if psychologist is None:
        raise exc.PsychologistNotFoundException(psychologist_id)
    
    # Проверка доступности психолога на указанное время
    if not await check_psychologist_availability(psychologist.id, scheduled_time_utc):
        raise exc.PsychologistUnavailableException(psychologist.id, scheduled_time_utc)

    match type:
        case AppointmentType.Offline:
            venue = psychologist.office
        case AppointmentType.Online:
            if venue is None:
                raise exc.VenueRequiredException()

    appointment = await repo_create_appointment(
        patient_id=patient_id,
        psychologist_id=psychologist.id,
        application_id=application_id,
        type=type,
        reason=reason,
        status=status,
        scheduled_time=scheduled_time_utc,
        remind_time=remind_time_utc,
        last_change_time=now,
        venue=venue,
        comment=comment,
    )

    if application_id:
        await confirm_application(
            application_id=application_id,
            appointment_id=appointment.id,
            actor_id=patient_id,
            is_owner=True
        )
        
    # Возвращаем полностью подгруженный объект
    return await repo_get_appointment_by_id(appointment.id, patient_id)


async def cancel_appointment_by_id(appointment_id: UUID) -> Appointment:
    # Этот метод скорее всего не используется напрямую из контроллеров без user_id
    # Оставляем как есть, если он где-то нужен внутри системных сервисов
    return await repo_cancel_appointment_by_id(appointment_id)


async def get_appointments_by_user_id(user_id: UUID) -> list[Appointment]:
    return await repo_get_appointments_by_user_id(user_id)


async def get_appointments_by_token(token: str) -> list[Appointment]:
    user_id = get_user_id_from_token(token)
    return await get_appointments_by_user_id(user_id)


async def cancel_appointment_by_member(appointment_id: UUID, user_id: UUID, cancel_reason: str) -> Appointment:
    appointment = await repo_cancel(appointment_id, user_id, cancel_reason)
    return appointment


async def get_appointment_for_user(appointment_id: UUID, user_id: UUID) -> Appointment | None:
    from psychohelp.repositories.appointments import get_appointment_for_user as repo_get
    appointment = await repo_get(appointment_id, user_id)
    return appointment


async def complete_appointment(
        appointment_id: UUID,
        psychologist_id: UUID,
        patient_comment: str,
        psychologist_comment: str | None = None) -> Appointment:
    from psychohelp.repositories.appointments import complete_appointment_by_psychologist as repo_complete
    appointment = await repo_complete(
        appointment_id,
        psychologist_id,
        patient_comment,
        psychologist_comment,
    )
    return appointment


async def request_appointment_reschedule(
    appointment_id: UUID,
    psychologist_user_id: UUID,
    scheduled_time: datetime,
    remind_time: datetime | None = None,
    venue: str | None = None,
    comment: str | None = None,
):
    scheduled_time_utc, remind_time_utc = _validate_appointment_time(scheduled_time, remind_time)

    psychologist = await get_psychologist_by_user_id(psychologist_user_id)
    if psychologist is None:
        raise exc.PsychologistNotFoundException(psychologist_user_id)
    
    if not await check_psychologist_availability(psychologist.id, scheduled_time_utc):
        raise exc.PsychologistUnavailableException(psychologist.id, scheduled_time_utc)
    
    return await reschedule_repo.create_reschedule_request(
        appointment_id=appointment_id,
        psychologist_user_id=psychologist_user_id,
        scheduled_time=scheduled_time_utc,
        remind_time=remind_time_utc,
        venue=venue,
        comment=comment,
    )


async def get_appointment_reschedule_requests(
    appointment_id: UUID,
    user_id: UUID,
):
    return await reschedule_repo.get_reschedule_requests_by_appointment(
        appointment_id=appointment_id,
        user_id=user_id,
    )


async def confirm_appointment_reschedule(
    request_id: UUID,
    patient_user_id: UUID,
):
    return await reschedule_repo.confirm_reschedule_request(
        request_id=request_id,
        patient_user_id=patient_user_id,
    )


async def reject_appointment_reschedule(
    request_id: UUID,
    patient_user_id: UUID,
    rejection_comment: str,
):
    return await reschedule_repo.reject_reschedule_request(
        request_id=request_id,
        patient_user_id=patient_user_id,
        rejection_comment=rejection_comment,
    )
