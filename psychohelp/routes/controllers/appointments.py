from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from pydantic import BaseModel

from starlette.status import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
)

from psychohelp.schemas.errors import error_responses
from psychohelp.config.logging import (
    get_logger,
)
from psychohelp.constants.rbac import (
    PermissionCode,
    RoleCode,
)
from psychohelp.dependencies.auth import (
    get_current_user,
    get_optional_user,
)
from psychohelp.models.users import User
from psychohelp.schemas.appointments import (
    AppointmentBase,
    AppointmentCancelRequest,
    AppointmentCreateRequest,
    AppointmentDoneRequest,
    AppointmentEmergencyContactRequest,
    AppointmentRescheduleCancelRequest,
    AppointmentRescheduleRequestCreate,
    AppointmentRescheduleRequestResponse,
)
from psychohelp.services.appointments import (
    exceptions as exc,
)
from psychohelp.services.appointments.appointments import (
    cancel_appointment_by_member,
    cancel_appointment_reschedule,
    complete_appointment,
    confirm_appointment_reschedule,
    create_appointment as srv_create_appointment,
    get_appointment_by_id,
    get_appointment_reschedule_requests,
    get_appointments_by_user_id,
    reassign_appointment_to_self,
    reject_appointment_reschedule,
    request_appointment_reschedule,
    update_emergency_contact,
)
from psychohelp.services.rbac.permissions import (
    require_permission,
)


logger = get_logger(__name__)

router = APIRouter(
    prefix="/appointments",
    tags=["appointments"],
)


@router.get(
    "/", responses=error_responses(401, 403),
    response_model=list[AppointmentBase],
)
async def get_appointments(
    user_id: UUID | None = None,
    current_user: User = Depends(
        get_optional_user
    ),
) -> list[AppointmentBase]:
    if user_id is None:
        if current_user is None:
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="Пользователь не авторизован",
            )

        return await get_appointments_by_user_id(
            current_user.id
        )

    if current_user is None:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Пользователь не авторизован",
        )

    if (
        current_user.id != user_id
        and not getattr(
            current_user,
            "is_admin",
            False,
        )
    ):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=(
                "Недостаточно прав для просмотра "
                "записей другого пользователя"
            ),
        )

    return await get_appointments_by_user_id(
        user_id
    )


@router.post(
    "/create", responses=error_responses(400, 401, 403, 404),
    response_model=AppointmentBase,
    status_code=HTTP_201_CREATED,
)
@require_permission(
    PermissionCode.APPOINTMENTS_CREATE_OWN
)
async def create_appointment(
    appointment: AppointmentCreateRequest,
    current_user: User = Depends(
        get_current_user
    ),
) -> AppointmentBase:
    try:
        if (
            appointment.patient_id
            != current_user.id
        ):
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail=(
                    "Вы можете создавать записи "
                    "только для себя"
                ),
            )

        created_appointment = (
            await srv_create_appointment(
                **appointment.model_dump()
            )
        )

        return created_appointment

    except exc.InvalidScheduledTimeException:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=(
                "Время записи не может быть в прошлом"
            ),
        )

    except exc.InvalidRemindTimeException as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=(
                "Некорректное время напоминания: "
                f"{e.reason}"
            ),
        )

    except exc.PatientNotFoundException:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Пациент не найден",
        )

    except exc.ApplicationNotFoundException:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Заявка не найдена",
        )

    except exc.PsychologistNotFoundException:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Психолог не найден",
        )

    except exc.VenueRequiredException:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=(
                "Необходимо указать место "
                "для онлайн встречи"
            ),
        )

    except exc.PsychologistUnavailableException as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=(
                "Психолог в отпуске или на больничном "
                f"в указанное время: {e.scheduled_time}"
            ),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/{id}", responses=error_responses(401, 403, 404),
    response_model=AppointmentBase,
)
@require_permission(
    PermissionCode.APPOINTMENTS_VIEW_OWN
)
async def get_appointment(
    id: UUID,
    current_user: User = Depends(
        get_current_user
    ),
) -> AppointmentBase:
    appointment = await get_appointment_by_id(
        id,
        current_user.id,
    )

    if appointment is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Встреча не найдена",
        )

    return appointment


@router.patch(
    "/{id}/emergency-contact",
    response_model=AppointmentBase,
    summary="Изменить или очистить экстренный контакт",
    responses=error_responses(401, 404, 409),
)
async def update_emergency_contact_endpoint(
    id: UUID,
    request: AppointmentEmergencyContactRequest,
    current_user: User = Depends(get_current_user),
) -> AppointmentBase:
    """Участники могут менять контакт в awaiting-записи; null очищает поле."""
    try:
        return await update_emergency_contact(id, current_user.id, request.emergency_contact)
    except exc.AppointmentNotFoundException:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Встреча не найдена")
    except exc.AppointmentNotActiveException as e:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(e))

class MessageResponse(BaseModel):
    message: str


@router.put("/{id}/cancel", responses=error_responses(400, 401, 403), response_model=MessageResponse)
@require_permission(PermissionCode.APPOINTMENTS_CANCEL_OWN)
async def cancel_appointment(
        id: UUID,
        request: AppointmentCancelRequest,
        current_user: User = Depends(get_current_user)
) -> MessageResponse:
    """Отменить запись на прием (для пациента)"""
    try:
        await cancel_appointment_by_member(id, current_user.id, request.cancel_reason)
        logger.info(f"Appointment cancelled: {id} by user: {current_user.id}. Reason: {request.cancel_reason}")
        return MessageResponse(message="Запись успешно отменена")

    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{id}/reassign", responses=error_responses(401, 403, 404, 409),
    response_model=AppointmentBase,
    summary="Переназначить запись на текущего психолога",
    description="Доступно любому психологу с профилем для записи в статусе awaiting "
    "со временем встречи строго в будущем. Если время уже наступило, возвращается 409. "
    "Если новый психолог в отпуске, на больничном или уже имеет ожидающую встречу "
    "на это время, возвращается 409 без изменения записи. "
    "Связанная заявка обновляется, ожидающие запросы переноса отклоняются. "
    "Повторный запрос назначенного психолога возвращает текущую запись.",
)
async def reassign_appointment(
    id: UUID,
    current_user: User = Depends(
        get_current_user
    ),
) -> AppointmentBase:
    if not any(
        role.code == RoleCode.PSYCHOLOGIST
        for role in (current_user.roles or [])
    ):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=(
                "Только психолог может "
                "переназначить запись на себя"
            ),
        )

    try:
        return await reassign_appointment_to_self(
            id,
            current_user.id,
        )

    except PermissionError as e:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=str(e),
        )

    except exc.AppointmentNotFoundException as e:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    except exc.PsychologistUnavailableException as e:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail=str(e),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.get(
    "/{id}/reschedule-requests", responses=error_responses(401, 403, 404),
    response_model=list[
        AppointmentRescheduleRequestResponse
    ],
)
@require_permission(
    PermissionCode.APPOINTMENTS_VIEW_OWN
)
async def get_reschedule_requests(
    id: UUID,
    current_user: User = Depends(
        get_current_user
    ),
) -> list[
    AppointmentRescheduleRequestResponse
]:
    try:
        return (
            await get_appointment_reschedule_requests(
                id,
                current_user.id,
            )
        )

    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post(
    "/{id}/reschedule-requests", responses=error_responses(400, 401, 403, 404),
    response_model=(
        AppointmentRescheduleRequestResponse
    ),
    status_code=HTTP_201_CREATED,
)
@require_permission(
    PermissionCode.APPOINTMENTS_RESCHEDULE
)
async def request_reschedule(
    id: UUID,
    request: AppointmentRescheduleRequestCreate,
    current_user: User = Depends(
        get_current_user
    ),
) -> AppointmentRescheduleRequestResponse:
    try:
        return await request_appointment_reschedule(
            appointment_id=id,
            psychologist_user_id=(
                current_user.id
            ),
            scheduled_time=(
                request.scheduled_time
            ),
            remind_time=request.remind_time,
            venue=request.venue,
            comment=request.comment,
        )

    except exc.InvalidScheduledTimeException:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=(
                "Время записи не может быть в прошлом"
            ),
        )

    except exc.InvalidRemindTimeException as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=(
                "Некорректное время напоминания: "
                f"{e.reason}"
            ),
        )

    except PermissionError as e:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=str(e),
        )

    except exc.PsychologistNotFoundException as e:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except exc.PsychologistUnavailableException:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=(
                "Вы находитесь в отпуске или "
                "на больничном в указанное время переноса"
            ),
        )


@router.post(
    "/reschedule-requests/{request_id}/confirm", responses=error_responses(400, 401, 403),
    response_model=(
        AppointmentRescheduleRequestResponse
    ),
)
@require_permission(
    PermissionCode.APPOINTMENTS_CONFIRM_OWN
)
async def confirm_reschedule(
    request_id: UUID,
    current_user: User = Depends(
        get_current_user
    ),
) -> AppointmentRescheduleRequestResponse:
    try:
        return await confirm_appointment_reschedule(
            request_id,
            current_user.id,
        )

    except PermissionError as e:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=str(e),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/reschedule-requests/{request_id}/cancel", responses=error_responses(400, 401, 403),
    response_model=(
        AppointmentRescheduleRequestResponse
    ),
)
@require_permission(
    PermissionCode.APPOINTMENTS_CONFIRM_OWN
)
async def cancel_reschedule(
    request_id: UUID,
    request: AppointmentRescheduleCancelRequest,
    current_user: User = Depends(
        get_current_user
    ),
) -> AppointmentRescheduleRequestResponse:
    try:
        return await cancel_appointment_reschedule(
            request_id,
            current_user.id,
            request.rejection_comment,
        )

    except PermissionError as e:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=str(e),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/reschedule-requests/{request_id}/reject", responses=error_responses(400, 401, 403),
    response_model=(
        AppointmentRescheduleRequestResponse
    ),
    deprecated=True,
)
@require_permission(
    PermissionCode.APPOINTMENTS_CONFIRM_OWN
)
async def reject_reschedule(
    request_id: UUID,
    request: AppointmentRescheduleCancelRequest,
    current_user: User = Depends(
        get_current_user
    ),
) -> AppointmentRescheduleRequestResponse:
    try:
        return await reject_appointment_reschedule(
            request_id,
            current_user.id,
            request.rejection_comment,
        )

    except PermissionError as e:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=str(e),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.put("/{id}/done", responses=error_responses(400, 401, 403), response_model=MessageResponse, summary="Завершить прием и сохранить комментарии")
async def complete_appointment_endpoint(
        id: UUID,
        request: AppointmentDoneRequest,
        current_user: User = Depends(get_current_user)
) -> MessageResponse:
    """
     Завершает запись на прием (переводит в статус Done).
     Доступно только психологу, который вел этот прием.
     Сохраняет комментарий пациенту и внутренний комментарий психологам.
     """
    try:
        await complete_appointment(
            id,
            current_user.id,
            request.patient_comment,
            request.psychologist_comment,
        )
        logger.info(f"Appointment completed: {id} by psychologist: {current_user.id}")
        return MessageResponse(message="Запись успешно завершена")

    except PermissionError as e:
        logger.warning(
            f"User {current_user.id} tried "
            f"to complete appointment {id}"
        )

        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=str(e),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
