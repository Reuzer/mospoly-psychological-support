from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from psychohelp.constants.rbac import RoleCode
from psychohelp.models.appointments import (
    Appointment,
    AppointmentStatus,
    AppointmentType,
)
from psychohelp.repositories import (
    get_user_id_from_token,
)
from psychohelp.repositories import (
    appointment_reschedule_requests as reschedule_repo,
)
from psychohelp.repositories.appointments import (
    cancel_appointment_by_id as repo_cancel,
    create_appointment as repo_create_appointment,
    get_appointment_by_id as repo_get_appointment_by_id,
    get_appointments_by_user_id as repo_get_appointments_by_user_id,
    is_appointment_slot_available,
    reassign_appointment_to_psychologist as repo_reassign_appointment_to_psychologist,
    update_emergency_contact as repo_update_emergency_contact,
)
from psychohelp.repositories.psychologists.psychologists import (
    check_psychologist_availability,
    get_psychologist_by_id,
    get_psychologist_by_user_id,
)
from psychohelp.repositories.users import (
    get_user_by_id,
)
from psychohelp.services.appointments import (
    exceptions as exc,
)


def _is_slot_conflict(error: IntegrityError) -> bool:
    original_error = error.orig
    cause = getattr(original_error, "__cause__", None)
    constraint_name = getattr(original_error, "constraint_name", None)
    if constraint_name is None and cause is not None:
        constraint_name = getattr(cause, "constraint_name", None)
    return constraint_name == "uq_appointments_psychologist_scheduled_active"


def _as_utc(
    value: datetime,
) -> datetime:
    if value.tzinfo:
        return value.astimezone(
            timezone.utc
        )

    return value.replace(
        tzinfo=timezone.utc
    )


def _validate_appointment_time(
    scheduled_time: datetime,
    remind_time: datetime | None,
) -> tuple[
    datetime,
    datetime | None,
]:
    now = datetime.now(timezone.utc)

    scheduled_time_utc = _as_utc(
        scheduled_time
    )

    if scheduled_time_utc <= now:
        raise exc.InvalidScheduledTimeException(
            scheduled_time
        )

    remind_time_utc = None

    if remind_time is not None:
        remind_time_utc = _as_utc(
            remind_time
        )

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

    return (
        scheduled_time_utc,
        remind_time_utc,
    )


async def get_appointment_by_id(
    appointment_id: UUID,
    user_id: UUID,
) -> Appointment | None:
    return await repo_get_appointment_by_id(
        appointment_id,
        user_id,
    )


async def update_emergency_contact(
    appointment_id: UUID, user_id: UUID, emergency_contact: str | None,
) -> Appointment:
    return await repo_update_emergency_contact(appointment_id, user_id, emergency_contact)


async def create_appointment(
    patient_id: UUID,
    psychologist_id: UUID,
    type: AppointmentType,
    scheduled_time: datetime,
    duration: int = 60,
    reason: str | None = None,
    remind_time: datetime | None = None,
    venue: str | None = None,
    comment: str | None = None,
) -> Appointment:
    now = datetime.now(timezone.utc)

    status = AppointmentStatus.awaiting

    (
        scheduled_time_utc,
        remind_time_utc,
    ) = _validate_appointment_time(
        scheduled_time,
        remind_time,
    )

    patient = await get_user_by_id(
        patient_id
    )

    if patient is None:
        raise exc.PatientNotFoundException(
            patient_id
        )

    psychologist = (
        await get_psychologist_by_id(
            psychologist_id
        )
    )

    if psychologist is None:
        psychologist = (
            await get_psychologist_by_user_id(
                psychologist_id
            )
        )

    if psychologist is None:
        raise exc.PsychologistNotFoundException(
            psychologist_id
        )

    if not await check_psychologist_availability(
        psychologist.id,
        scheduled_time_utc,
    ):
        raise exc.PsychologistUnavailableException(
            psychologist.id,
            scheduled_time_utc,
        )

    if not await is_appointment_slot_available(
        psychologist.id,
        scheduled_time_utc,
    ):
        raise exc.AppointmentSlotOccupiedException(
            psychologist.id,
            scheduled_time_utc,
        )

    match type:
        case AppointmentType.Offline:
            venue = psychologist.office

        case AppointmentType.Online:
            if venue is None:
                raise exc.VenueRequiredException()

    try:
        appointment = await repo_create_appointment(
            patient_id=patient_id,
            psychologist_id=psychologist.id,
            type=type,
            duration=duration,
            reason=reason,
            status=status,
            scheduled_time=scheduled_time_utc,
            remind_time=remind_time_utc,
            last_change_time=now,
            venue=venue,
            comment=comment,
        )
    except IntegrityError as error:
        if _is_slot_conflict(error):
            raise exc.AppointmentSlotOccupiedException(
                psychologist.id,
                scheduled_time_utc,
            ) from error
        raise

    return await repo_get_appointment_by_id(
        appointment.id,
        patient_id,
    )


async def get_appointments_by_user_id(
    user_id: UUID,
) -> list[Appointment]:
    return await repo_get_appointments_by_user_id(
        user_id
    )


async def reassign_appointment_to_self(
    appointment_id: UUID,
    psychologist_user_id: UUID,
) -> Appointment:
    """
    Переназначить ожидающую запись
    на психолога, выполняющего действие.
    """

    actor = await get_user_by_id(
        psychologist_user_id
    )

    if actor is None or not any(
        role.code == RoleCode.PSYCHOLOGIST
        for role in (actor.roles or [])
    ):
        raise PermissionError(
            "Только психолог может "
            "переназначить запись на себя"
        )

    psychologist = (
        await get_psychologist_by_user_id(
            psychologist_user_id
        )
    )

    if psychologist is None:
        raise PermissionError(
            "Для переназначения необходим "
            "профиль психолога"
        )

    return (
        await repo_reassign_appointment_to_psychologist(
            appointment_id=appointment_id,
            psychologist_user_id=(
                psychologist_user_id
            ),
        )
    )


async def get_appointments_by_token(
    token: str,
) -> list[Appointment]:
    user_id = get_user_id_from_token(
        token
    )

    return await get_appointments_by_user_id(
        user_id
    )


async def cancel_appointment_by_member(
    appointment_id: UUID,
    user_id: UUID,
    cancel_reason: str,
    is_emergency: bool = False,
) -> Appointment:
    return await repo_cancel(
        appointment_id,
        user_id,
        cancel_reason,
        is_emergency,
    )


async def get_appointment_for_user(
    appointment_id: UUID,
    user_id: UUID,
) -> Appointment | None:
    from psychohelp.repositories.appointments import (
        get_appointment_for_user as repo_get,
    )

    return await repo_get(
        appointment_id,
        user_id,
    )


async def complete_appointment(
    appointment_id: UUID,
    psychologist_id: UUID,
    patient_comment: str | None = None,
    psychologist_comment: str | None = None,
) -> Appointment:
    from psychohelp.repositories.appointments import (
        complete_appointment_by_psychologist as repo_complete,
    )

    return await repo_complete(
        appointment_id,
        psychologist_id,
        patient_comment,
        psychologist_comment,
    )


async def request_appointment_reschedule(
    appointment_id: UUID,
    psychologist_user_id: UUID,
    scheduled_time: datetime,
    remind_time: datetime | None = None,
    venue: str | None = None,
    comment: str | None = None,
):
    (
        scheduled_time_utc,
        remind_time_utc,
    ) = _validate_appointment_time(
        scheduled_time,
        remind_time,
    )

    psychologist = (
        await get_psychologist_by_user_id(
            psychologist_user_id
        )
    )

    if psychologist is None:
        raise exc.PsychologistNotFoundException(
            psychologist_user_id
        )

    if not await check_psychologist_availability(
        psychologist.id,
        scheduled_time_utc,
    ):
        raise exc.PsychologistUnavailableException(
            psychologist.id,
            scheduled_time_utc,
        )

    if not await is_appointment_slot_available(
        psychologist.id,
        scheduled_time_utc,
    ):
        raise exc.AppointmentSlotOccupiedException(
            psychologist.id,
            scheduled_time_utc,
        )

    return (
        await reschedule_repo.create_reschedule_request(
            appointment_id=appointment_id,
            psychologist_user_id=(
                psychologist_user_id
            ),
            scheduled_time=scheduled_time_utc,
            remind_time=remind_time_utc,
            venue=venue,
            comment=comment,
        )
    )


async def get_appointment_reschedule_requests(
    appointment_id: UUID,
    user_id: UUID,
):
    return (
        await reschedule_repo.get_reschedule_requests_by_appointment(
            appointment_id=appointment_id,
            user_id=user_id,
        )
    )


async def confirm_appointment_reschedule(
    request_id: UUID,
    patient_user_id: UUID,
):
    try:
        return await reschedule_repo.confirm_reschedule_request(
            request_id=request_id,
            patient_user_id=patient_user_id,
        )
    except IntegrityError as error:
        if _is_slot_conflict(error):
            raise exc.AppointmentSlotOccupiedException(None, None) from error
        raise


async def reject_appointment_reschedule(
    request_id: UUID,
    patient_user_id: UUID,
    rejection_comment: str,
):
    return await cancel_appointment_reschedule(
        request_id=request_id,
        patient_user_id=patient_user_id,
        rejection_comment=rejection_comment,
    )


async def cancel_appointment_reschedule(
    request_id: UUID,
    patient_user_id: UUID,
    rejection_comment: str,
):
    return (
        await reschedule_repo.cancel_reschedule_request(
            request_id=request_id,
            patient_user_id=patient_user_id,
            rejection_comment=rejection_comment,
        )
    )
