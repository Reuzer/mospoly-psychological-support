from uuid import UUID
from fastapi import APIRouter, Query, Request, HTTPException, Depends
from starlette.status import (
    HTTP_201_CREATED, HTTP_200_OK, HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND, HTTP_409_CONFLICT
)
from typing import Optional

from psychohelp.config.logging import get_logger
from psychohelp.services.applications.applications import (
    create_application,
    get_application_for_user,
    accept_to_processing,
    offer_consultation,
    confirm_application,
    reject_application,
    cancel_application,
    get_applications_list
)
from psychohelp.services.applications.exceptions import (
    ApplicationNotFoundError, InvalidStatusTransitionError, AccessDeniedError,
    ConflictError, ValidationError
)
from psychohelp.repositories.applications import get_applications as repo_get_applications
from psychohelp.schemas.applications import (
    ApplicationCreateRequest,
    ApplicationResponse,
    ApplicationStatus,
    AcceptToProcessingRequest,
    OfferConsultationRequest,
    RejectRequest,
    CancelRequest, UniversityStatus,
)
from psychohelp.services.rbac.permissions import require_permission
from psychohelp.constants.rbac import PermissionCode
from psychohelp.repositories import get_user_id_from_token
from psychohelp.dependencies.auth import get_current_user
from psychohelp.models.users import User
from psychohelp.repositories.users import get_user_by_id

logger = get_logger(__name__)
router = APIRouter(prefix="/applications", tags=["applications"])


@router.get(
    "/university-statuses",
    summary="Получить статусы в университете",
    description="Возвращает допустимые статусы заявителя в университете для заполнения заявки.",
)
async def get_university_statuses() -> list[str]:
    """
        Возвращает список всех доступных статусов в университете
        (студент, аспирант и т.д.) для выпадающего списка на фронтенде.
    """
    return [status.value for status in UniversityStatus]


# Вспомогательные функции проверки прав (можно вынести в отдельный модуль)
async def _is_manager_or_psychologist(user_id: UUID) -> bool:
    user = await get_user_by_id(user_id)
    if not user:
        return False
    roles = [role.code.value for role in user.roles]
    return "manager" in roles or "psychologist" in roles  # зависит от ваших кодов ролей


async def _is_psychologist(user_id: UUID) -> bool:
    user = await get_user_by_id(user_id)
    if not user:
        return False
    roles = [role.code.value for role in user.roles]
    return "psychologist" in roles



# 1. Создание заявки (открыто для всех)
@router.post(
    "/",
    response_model=ApplicationResponse,
    status_code=HTTP_201_CREATED,
    summary="Создать заявку на консультацию",
    description=(
        "Создаёт заявку на психологическую консультацию для текущего пользователя и возвращает её "
        "данные. Требуется авторизация."
    ),
)
async def create_application_endpoint(
    request: Request,
    data: ApplicationCreateRequest
) -> ApplicationResponse:
    token = request.cookies.get("access_token")
    if token:
        user_id = get_user_id_from_token(token)
        application = await create_application(user_id, data)
        logger.info(f"Application created: {application.id}")
        return ApplicationResponse.from_orm(application)
    else:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Недостаточно прав")


# 2. Получение списка заявок (только для руководителей/психологов, с фильтрацией)
@router.get(
    "/",
    response_model=list[ApplicationResponse],
    summary="Получить список заявок",
    description=(
        "Возвращает заявки с пагинацией, фильтрацией и сортировкой. Пользователь видит свои "
        "заявки, руководитель или психолог — заявки всех пользователей."
    ),
)
async def get_applications(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[ApplicationStatus] = None,
    assigned_to: Optional[UUID] = None,
    sort_by: str = "created_at",
    sort_desc: bool = True,
    current_user: User = Depends(get_current_user)
) -> list[ApplicationResponse]:
    
    is_staff = await _is_manager_or_psychologist(current_user.id)
    
    applications = await get_applications_list(
        skip=skip, 
        limit=limit, 
        status=status,
        assigned_to=assigned_to,
        current_user_id=current_user.id,
        is_manager_or_psychologist=is_staff,
        sort_by=sort_by, 
        sort_desc=sort_desc
    )
    
    return [ApplicationResponse.from_orm(app) for app in applications]


# 3. Получение конкретной заявки (с проверкой прав)
@router.get(
    "/{application_id}",
    response_model=ApplicationResponse,
    summary="Получить заявку по ID",
    description=(
        "Возвращает данные заявки по её идентификатору. Доступна владельцу заявки, руководителю "
        "или психологу."
    ),
)
async def get_application(
    request: Request,
    application_id: UUID,
    current_user: User = Depends(get_current_user)
) -> ApplicationResponse:
    is_manager = await _is_manager_or_psychologist(current_user.id)
    application = await get_application_for_user(application_id, current_user.id, is_manager)
    return ApplicationResponse.from_orm(application)


# 4. Принять в обработку
@router.post(
    "/{application_id}/accept",
    response_model=ApplicationResponse,
    summary="Принять заявку в обработку",
    description=(
        "Переводит новую заявку в обработку и назначает ответственного. Доступно руководителю или "
        "психологу; возвращает обновлённую заявку."
    ),
)
async def accept_application(
    application_id: UUID,
    data: AcceptToProcessingRequest,
    current_user: User = Depends(get_current_user)
) -> ApplicationResponse:
    is_allowed = await _is_manager_or_psychologist(current_user.id)
    try:
        updated = await accept_to_processing(
            application_id, data.assigned_to, current_user.id, is_allowed
        )
        return ApplicationResponse.from_orm(updated)
    except ApplicationNotFoundError:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Заявка не найдена")
    except AccessDeniedError:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(e))


# 5. Предложить условия консультации
@router.post(
    "/{application_id}/offer",
    response_model=ApplicationResponse,
    summary="Предложить условия консультации",
    description=(
        "Сохраняет психолога, время, формат и место консультации в заявке и переводит её в "
        "ожидание подтверждения пользователя. Доступно психологу."
    ),
)
async def offer_consultation_endpoint(
    application_id: UUID,
    data: OfferConsultationRequest,
    current_user: User = Depends(get_current_user)
) -> ApplicationResponse:
    is_psych = await _is_psychologist(current_user.id)
    try:
        updated = await offer_consultation(application_id, data, current_user.id, is_psych)
        return ApplicationResponse.from_orm(updated)
    except ApplicationNotFoundError:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Заявка не найдена")
    except AccessDeniedError:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Только психолог может предложить консультацию")
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(e))


# 6. Подтверждение пользователя (создание Appointment)
@router.post(
    "/{application_id}/confirm",
    response_model=ApplicationResponse,
    summary="Подтвердить заявку",
    description=(
        "Подтверждает условия консультации и завершает обработку собственной заявки. Использует "
        "переданный appointment_id или уже связанную с заявкой запись на приём."
    ),
)
async def confirm_application_endpoint(
    application_id: UUID,
    appointment_id: UUID | None = None, # Оставляем как опциональный Query-параметр
    current_user: User = Depends(get_current_user)
) -> ApplicationResponse:
    
    application = await get_application_for_user(application_id, current_user.id, False)
    
    if not application or application.user_id != current_user.id:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Вы можете подтверждать только свои заявки")
        
    resolved_appointment_id = appointment_id or application.appointment_id
    
    try:
        updated = await confirm_application(
            application_id, resolved_appointment_id, current_user.id, is_owner=True
        )
        return ApplicationResponse.from_orm(updated)
        
    except ApplicationNotFoundError:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Заявка не найдена")
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(e))
    except ValidationError as e:
        # ИСПРАВЛЕНО: Теперь возвращаем 400 и реальный текст ошибки от State Machine
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(e))


# 7. Отклонить заявку
@router.post(
    "/{application_id}/reject",
    response_model=ApplicationResponse,
    summary="Отклонить заявку",
    description=(
        "Отклоняет новую или находящуюся в обработке заявку с указанием причины. Доступно "
        "руководителю или психологу; возвращает обновлённую заявку."
    ),
)
async def reject_application_endpoint(
    application_id: UUID,
    data: RejectRequest,
    current_user: User = Depends(get_current_user)
) -> ApplicationResponse:
    is_allowed = await _is_manager_or_psychologist(current_user.id)
    try:
        updated = await reject_application(application_id, data.reject_reason, current_user.id, is_allowed)
        return ApplicationResponse.from_orm(updated)
    except ApplicationNotFoundError:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Заявка не найдена")
    except AccessDeniedError:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(e))


# 8. Отмена заявки
@router.post(
    "/{application_id}/cancel",
    response_model=ApplicationResponse,
    summary="Отменить заявку",
    description=(
        "Отменяет заявку с указанием причины и инициатора отмены. Требуется авторизация и доступ "
        "к заявке; возвращает обновлённую заявку."
    ),
)
async def cancel_application_endpoint(
    application_id: UUID,
    data: CancelRequest,
    request: Request,
    current_user: User = Depends(get_current_user)
) -> ApplicationResponse:
    # Определяем тип актора и права
    actor_type = "user"
    is_allowed = False
    if current_user.id:
        is_owner = (await get_application_for_user(application_id, current_user.id, False)).user_id == current_user.id
        if is_owner:
            is_allowed = True
            actor_type = "user"
        elif await _is_manager_or_psychologist(current_user.id):
            is_allowed = True
            actor_type = "psychologist" if await _is_psychologist(current_user.id) else "manager"
    if not is_allowed:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Недостаточно прав для отмены")
    try:
        updated = await cancel_application(
            application_id, data.cancel_reason, data.cancel_initiator,
            current_user.id, actor_type, is_allowed
        )
        return ApplicationResponse.from_orm(updated)
    except ApplicationNotFoundError:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Заявка не найдена")
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(e))
