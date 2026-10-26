from typing import Literal, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
)
from starlette.status import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
)

from psychohelp.schemas.errors import error_responses
from psychohelp.config.logging import get_logger
from psychohelp.dependencies.auth import get_current_user
from psychohelp.models.users import User
from psychohelp.repositories.users import (
    get_user_by_id,
)
from psychohelp.schemas.applications import (
    AcceptToProcessingRequest,
    ApplicationConfirmRequest,
    ApplicationCreateRequest,
    ApplicationReassignRequest,
    ApplicationResponse,
    ApplicationStatus,
    CancelRequest,
    OfferConsultationRequest,
    RejectRequest,
    UniversityStatus,
)
from psychohelp.services.applications.applications import (
    accept_to_processing,
    cancel_application,
    confirm_application,
    create_application,
    get_application_for_user,
    get_applications_list,
    offer_consultation,
    reassign_application,
    reject_application,
)
from psychohelp.services.applications.exceptions import (
    AccessDeniedError,
    ApplicationNotFoundError,
    ConflictError,
    InvalidStatusTransitionError,
    ValidationError,
)


logger = get_logger(__name__)

router = APIRouter(
    prefix="/applications",
    tags=["applications"],
)


@router.get(
    "/university-statuses",
    summary="Получить статусы в университете",
)
async def get_university_statuses() -> list[str]:
    return [
        status.value
        for status in UniversityStatus
    ]


async def _is_manager_or_psychologist(
    user_id: UUID,
) -> bool:
    user = await get_user_by_id(user_id)

    if not user:
        return False

    roles = [
        role.code.value
        for role in user.roles
    ]

    return (
        "manager" in roles
        or "psychologist" in roles
    )


async def _is_psychologist(
    user_id: UUID,
) -> bool:
    user = await get_user_by_id(user_id)

    if not user:
        return False

    roles = [
        role.code.value
        for role in user.roles
    ]

    return "psychologist" in roles


@router.post(
    "/", responses=error_responses(401, 404),
    response_model=ApplicationResponse,
    status_code=HTTP_201_CREATED,
)
async def create_application_endpoint(
    data: ApplicationCreateRequest,
    current_user: User = Depends(get_current_user),
) -> ApplicationResponse:
    application = await create_application(
        current_user.id,
        data,
    )

    logger.info(
        f"Application created: {application.id}"
    )

    return ApplicationResponse.from_orm(
        application
    )


@router.get(
    "/", responses=error_responses(401),
    response_model=list[ApplicationResponse],
)
async def get_applications(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[ApplicationStatus] = None,
    assigned_to: Optional[UUID] = None,
    sort_by: Literal["created_at", "updated_at", "scheduled_at", "status"] = "created_at",
    sort_desc: bool = True,
    current_user: User = Depends(
        get_current_user
    ),
) -> list[ApplicationResponse]:
    is_staff = (
        await _is_manager_or_psychologist(
            current_user.id
        )
    )

    applications = await get_applications_list(
        skip=skip,
        limit=limit,
        status=status,
        assigned_to=assigned_to,
        current_user_id=current_user.id,
        is_manager_or_psychologist=is_staff,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )

    return [
        ApplicationResponse.from_orm(app)
        for app in applications
    ]


@router.get(
    "/{application_id}", responses=error_responses(401, 403, 404),
    response_model=ApplicationResponse,
)
async def get_application(
    request: Request,
    application_id: UUID,
    current_user: User = Depends(
        get_current_user
    ),
) -> ApplicationResponse:
    is_manager = (
        await _is_manager_or_psychologist(
            current_user.id
        )
    )

    application = await get_application_for_user(
        application_id,
        current_user.id,
        is_manager,
    )

    return ApplicationResponse.from_orm(
        application
    )


@router.post(
    "/{application_id}/accept", responses=error_responses(400, 401, 403, 404, 409),
    response_model=ApplicationResponse,
)
async def accept_application(
    application_id: UUID,
    data: AcceptToProcessingRequest,
    current_user: User = Depends(
        get_current_user
    ),
) -> ApplicationResponse:
    is_allowed = (
        await _is_manager_or_psychologist(
            current_user.id
        )
    )

    try:
        updated = await accept_to_processing(
            application_id,
            data.assigned_to,
            current_user.id,
            is_allowed,
        )

        return ApplicationResponse.from_orm(
            updated
        )

    except ApplicationNotFoundError:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Заявка не найдена",
        )

    except AccessDeniedError:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Недостаточно прав",
        )

    except InvalidStatusTransitionError as e:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail=str(e),
        )

    except ConflictError as e:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail=str(e),
        )

    except ValidationError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{application_id}/offer", responses=error_responses(400, 401, 403, 404, 409),
    response_model=ApplicationResponse,
)
async def offer_consultation_endpoint(
    application_id: UUID,
    data: OfferConsultationRequest,
    current_user: User = Depends(
        get_current_user
    ),
) -> ApplicationResponse:
    is_psych = await _is_psychologist(
        current_user.id
    )

    try:
        updated = await offer_consultation(
            application_id,
            data,
            current_user.id,
            is_psych,
        )

        return ApplicationResponse.from_orm(
            updated
        )

    except ApplicationNotFoundError:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Заявка не найдена",
        )

    except AccessDeniedError:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=(
                "Только психолог может "
                "предложить консультацию"
            ),
        )

    except InvalidStatusTransitionError as e:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail=str(e),
        )

    except ConflictError as e:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail=str(e),
        )

    except ValidationError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{application_id}/reassign", responses=error_responses(400, 401, 403, 404, 409),
    response_model=ApplicationResponse,
    summary=(
        "Переназначить заявку на себя "
        "и повторно запросить подтверждение"
    ),
    description="Любой психолог с профилем может изменить условия заявки в статусе "
    "awaiting_user_confirmation и назначить её на себя. Пустое тело {} сохраняет "
    "условия встречи. Версия предложения увеличивается; пользователь должен "
    "подтвердить новую версию через /confirm.",
)
async def reassign_application_endpoint(
    application_id: UUID,
    data: ApplicationReassignRequest,
    current_user: User = Depends(
        get_current_user
    ),
) -> ApplicationResponse:
    try:
        application = await reassign_application(
            application_id,
            data,
            current_user.id,
        )

        return ApplicationResponse.from_orm(
            application
        )

    except AccessDeniedError as e:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=str(e),
        )

    except ApplicationNotFoundError:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Заявка не найдена",
        )

    except (
        InvalidStatusTransitionError,
        ConflictError,
    ) as e:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail=str(e),
        )

    except ValidationError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{application_id}/confirm", responses=error_responses(400, 401, 403, 404, 409),
    response_model=ApplicationResponse,
    summary="Подтвердить актуальную версию предложения",
    description="Только владелец заявки. При совпадении expected_version и version "
    "сервер атомарно создаёт запись из сохранённых условий. Устаревшая версия "
    "или повторное подтверждение возвращают 409.",
)
async def confirm_application_endpoint(
    application_id: UUID,
    data: ApplicationConfirmRequest,
    current_user: User = Depends(
        get_current_user
    ),
) -> ApplicationResponse:
    try:
        updated = await confirm_application(
            application_id=application_id,
            expected_version=(
                data.expected_version
            ),
            actor_id=current_user.id,
            is_owner=True,
        )

        return ApplicationResponse.from_orm(
            updated
        )

    except ApplicationNotFoundError:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Заявка не найдена",
        )

    except AccessDeniedError as e:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=str(e),
        )

    except InvalidStatusTransitionError as e:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail=str(e),
        )

    except ConflictError as e:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail=str(e),
        )

    except ValidationError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{application_id}/reject", responses=error_responses(400, 401, 403, 404, 409),
    response_model=ApplicationResponse,
)
async def reject_application_endpoint(
    application_id: UUID,
    data: RejectRequest,
    current_user: User = Depends(
        get_current_user
    ),
) -> ApplicationResponse:
    is_allowed = (
        await _is_manager_or_psychologist(
            current_user.id
        )
    )

    try:
        updated = await reject_application(
            application_id,
            data.reject_reason,
            current_user.id,
            is_allowed,
        )

        return ApplicationResponse.from_orm(
            updated
        )

    except ApplicationNotFoundError:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Заявка не найдена",
        )

    except AccessDeniedError:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Недостаточно прав",
        )

    except InvalidStatusTransitionError as e:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail=str(e),
        )

    except ConflictError as e:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail=str(e),
        )

    except ValidationError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{application_id}/cancel", responses=error_responses(400, 401, 403, 404, 409),
    response_model=ApplicationResponse,
)
async def cancel_application_endpoint(
    application_id: UUID,
    data: CancelRequest,
    request: Request,
    current_user: User = Depends(
        get_current_user
    ),
) -> ApplicationResponse:
    actor_type = "user"
    is_allowed = False

    if current_user.id:
        application = (
            await get_application_for_user(
                application_id,
                current_user.id,
                await _is_manager_or_psychologist(current_user.id),
            )
        )

        is_owner = (
            application.user_id
            == current_user.id
        )

        if is_owner:
            is_allowed = True
            actor_type = "user"

        elif await _is_manager_or_psychologist(
            current_user.id
        ):
            is_allowed = True

            actor_type = (
                "psychologist"
                if await _is_psychologist(
                    current_user.id
                )
                else "manager"
            )

    if not is_allowed:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=(
                "Недостаточно прав для отмены"
            ),
        )

    try:
        updated = await cancel_application(
            application_id,
            data.cancel_reason,
            data.cancel_initiator,
            current_user.id,
            actor_type,
            is_allowed,
        )

        return ApplicationResponse.from_orm(
            updated
        )

    except ApplicationNotFoundError:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Заявка не найдена",
        )

    except InvalidStatusTransitionError as e:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail=str(e),
        )

    except ConflictError as e:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail=str(e),
        )

    except ValidationError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
