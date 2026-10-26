from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from starlette.status import (
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
)

from psychohelp.constants.rbac import RoleCode
from psychohelp.models.applications import (
    Application,
    ApplicationStatus,
)
from psychohelp.repositories import applications as repo
from psychohelp.repositories.psychologists.psychologists import (
    check_psychologist_availability,
    get_psychologist_by_id,
    get_psychologist_by_user_id,
)
from psychohelp.repositories.users import get_user_by_id
from psychohelp.schemas.applications import (
    ApplicationCreateRequest,
    ApplicationReassignRequest,
    OfferConsultationRequest,
)
from psychohelp.services.applications.exceptions import (
    AccessDeniedError,
    ApplicationNotFoundError,
    ConflictError,
    InvalidStatusTransitionError,
    ValidationError,
)
from psychohelp.services.applications.state_machine import (
    ApplicationStateMachine,
)


def _validate_offer_payload(offer_payload: dict) -> None:
    """Проверить итоговые условия первоначального и повторного предложения."""
    scheduled_at = offer_payload["scheduled_at"]

    if scheduled_at is None:
        raise ValidationError(
            "Необходимо указать дату и время встречи"
        )

    scheduled_at = (
        scheduled_at.astimezone(timezone.utc)
        if scheduled_at.tzinfo
        else scheduled_at.replace(
            tzinfo=timezone.utc
        )
    )

    if scheduled_at <= datetime.now(timezone.utc):
        raise ValidationError(
            "Дата и время встречи не могут быть в прошлом"
        )

    offer_payload["scheduled_at"] = scheduled_at

    meeting_type = offer_payload["meeting_type"]

    if meeting_type == "offline":
        if not (
            offer_payload["location_address"] or ""
        ).strip():
            raise ValidationError(
                "Для очной встречи необходимо указать адрес"
            )

        offer_payload["meeting_url"] = None

    elif meeting_type == "online":
        if not (
            offer_payload["meeting_url"] or ""
        ).strip():
            raise ValidationError(
                "Для онлайн-встречи необходимо указать ссылку"
            )

        offer_payload["location_address"] = None

    else:
        raise ValidationError(
            "Необходимо указать формат встречи"
        )

    venue = (
        offer_payload["location_address"]
        if meeting_type == "offline"
        else offer_payload["meeting_url"]
    ).strip()
    if len(venue) > 128:
        raise ValidationError(
            "Место встречи или ссылка не могут быть длиннее 128 символов"
        )


async def create_application(
    user_id: UUID,
    data: ApplicationCreateRequest,
) -> Application:
    application_dict = data.model_dump()

    user = await get_user_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    application_dict["user_id"] = user_id

    created_app = await repo.create_application(
        application_dict
    )

    return await repo.get_application_by_id(
        created_app.id
    )


async def get_application_for_user(
    application_id: UUID,
    user_id: UUID | None,
    is_manager_or_psychologist: bool,
) -> Application:
    application = await repo.get_application_by_id(
        application_id
    )

    if not application:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    if (
        not is_manager_or_psychologist
        and application.user_id != user_id
    ):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return application


async def get_applications_list(
    skip: int,
    limit: int,
    status: ApplicationStatus | None,
    assigned_to: UUID | None,
    current_user_id: UUID,
    is_manager_or_psychologist: bool,
    sort_by: str = "created_at",
    sort_desc: bool = True,
) -> list[Application]:
    query_user_id = None
    query_assigned_to = assigned_to

    if not is_manager_or_psychologist:
        query_user_id = current_user_id
        query_assigned_to = None

    return await repo.get_applications(
        skip=skip,
        limit=limit,
        status=status,
        assigned_to=query_assigned_to,
        user_id=query_user_id,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )


async def accept_to_processing(
    application_id: UUID,
    assigned_to: UUID,
    actor_id: UUID,
    is_allowed: bool,
) -> Application:
    if not is_allowed:
        raise AccessDeniedError()

    application = await repo.get_application_by_id(
        application_id
    )

    if not application:
        raise ApplicationNotFoundError()

    sm = ApplicationStateMachine(application)

    try:
        updated = await sm.accept_to_processing(
            assigned_to,
            actor_id,
            "psychologist"
            if is_allowed
            else "manager",
        )

        return await repo.get_application_by_id(
            updated.id
        )

    except (
        InvalidStatusTransitionError,
        ConflictError,
        ValidationError,
    ) as e:
        raise e


async def offer_consultation(
    application_id: UUID,
    offer_data: OfferConsultationRequest,
    actor_id: UUID,
    is_psychologist: bool,
) -> Application:
    if not is_psychologist:
        raise AccessDeniedError()

    application = await repo.get_application_by_id(
        application_id
    )

    if not application:
        raise ApplicationNotFoundError()

    psychologist = await get_psychologist_by_id(
        offer_data.psychologist_id
    )

    if psychologist is None:
        psychologist = (
            await get_psychologist_by_user_id(
                offer_data.psychologist_id
            )
        )

    if psychologist is None:
        raise ValidationError(
            "Психолог не найден"
        )

    offer_payload = offer_data.model_dump()
    offer_payload["psychologist_id"] = (
        psychologist.id
    )

    _validate_offer_payload(offer_payload)
    if not await check_psychologist_availability(
        psychologist.id, offer_payload["scheduled_at"],
    ):
        raise ValidationError(
            "Психолог в отпуске или на больничном в указанное время"
        )

    sm = ApplicationStateMachine(application)

    try:
        updated = await sm.offer_consultation(
            offer_payload,
            actor_id,
            "psychologist",
        )

        return await repo.get_application_by_id(
            updated.id
        )

    except (
        InvalidStatusTransitionError,
        ConflictError,
        ValidationError,
    ) as e:
        raise e


async def reassign_application(
    application_id: UUID,
    data: ApplicationReassignRequest,
    actor_id: UUID,
) -> Application:
    """
    Переназначить ожидающую подтверждения заявку
    на текущего психолога и повторно предложить условия.
    """

    actor = await get_user_by_id(actor_id)

    if actor is None or not any(
        role.code == RoleCode.PSYCHOLOGIST
        for role in (actor.roles or [])
    ):
        raise AccessDeniedError(
            "Переназначать заявки может только психолог"
        )

    psychologist = (
        await get_psychologist_by_user_id(actor_id)
    )

    if psychologist is None:
        raise AccessDeniedError(
            "Профиль психолога не найден"
        )

    application = await repo.get_application_by_id(
        application_id
    )

    if application is None:
        raise ApplicationNotFoundError()

    if (
        application.status
        != ApplicationStatus.AWAITING_USER_CONFIRMATION
    ):
        raise InvalidStatusTransitionError(
            "Переназначить заявку можно только "
            "на этапе подтверждения пользователя"
        )

    offer_payload = {
        "psychologist_id": psychologist.id,
        "meeting_type": application.meeting_type,
        "scheduled_at": application.scheduled_at,
        "location_address": (
            application.location_address
        ),
        "meeting_url": application.meeting_url,
    }

    offer_payload.update(
        data.model_dump(exclude_unset=True)
    )

    _validate_offer_payload(offer_payload)
    scheduled_at = offer_payload["scheduled_at"]

    if not await check_psychologist_availability(
        psychologist.id,
        scheduled_at,
    ):
        raise ValidationError(
            "Психолог в отпуске или на больничном "
            "в указанное время"
        )

    updated = await ApplicationStateMachine(
        application
    ).reassign(
        offer_payload,
        actor_id,
    )

    return await repo.get_application_by_id(
        updated.id
    )


async def confirm_application(
    application_id: UUID,
    expected_version: int,
    actor_id: UUID,
    is_owner: bool,
) -> Application:
    if not is_owner:
        raise AccessDeniedError()

    return (
        await repo.confirm_application_and_create_appointment(
            application_id=application_id,
            actor_id=actor_id,
            expected_version=expected_version,
        )
    )


async def reject_application(
    application_id: UUID,
    reject_reason: str,
    actor_id: UUID,
    is_allowed: bool,
) -> Application:
    if not is_allowed:
        raise AccessDeniedError()

    application = await repo.get_application_by_id(
        application_id
    )

    if not application:
        raise ApplicationNotFoundError()

    sm = ApplicationStateMachine(application)

    try:
        updated = await sm.reject(
            reject_reason,
            actor_id,
            "psychologist"
            if is_allowed
            else "manager",
        )

        return await repo.get_application_by_id(
            updated.id
        )

    except (
        InvalidStatusTransitionError,
        ConflictError,
        ValidationError,
    ) as e:
        raise e


async def cancel_application(
    application_id: UUID,
    cancel_reason: str,
    cancel_initiator: str,
    actor_id: UUID,
    actor_type: str,
    is_allowed: bool,
) -> Application:
    if not is_allowed:
        raise AccessDeniedError()

    application = await repo.get_application_by_id(
        application_id
    )

    if not application:
        raise ApplicationNotFoundError()

    sm = ApplicationStateMachine(application)

    try:
        updated = await sm.cancel(
            cancel_reason,
            cancel_initiator,
            actor_id,
            actor_type,
        )

        return await repo.get_application_by_id(
            updated.id
        )

    except (
        InvalidStatusTransitionError,
        ConflictError,
        ValidationError,
    ) as e:
        raise e


async def expire_application(
    application_id: UUID,
) -> Application:
    application = await repo.get_application_by_id(
        application_id
    )

    if not application:
        raise ApplicationNotFoundError()

    sm = ApplicationStateMachine(application)

    try:
        updated = await sm.expire(
            None,
            "system",
        )

        return await repo.get_application_by_id(
            updated.id
        )

    except (
        InvalidStatusTransitionError,
        ConflictError,
    ) as e:
        raise e
