import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
)

from psychohelp.models.users import User
from psychohelp.dependencies.auth import get_current_user
from psychohelp.services.rbac.permissions import user_has_permission
from psychohelp.constants.rbac import PermissionCode

from psychohelp.schemas.psychologist_statuses import (
    PsychologistStatusResponse,
    PsychologistStatusCreateRequest,
    CurrentStatusInfoResponse
)
from psychohelp.repositories.psychologist_statuses.exceptions import (
    OverlappingStatusException,
    InvalidStatusPeriodException,
    PsychologistStatusNotFound,
    UserIsNotPsychologist
)
from psychohelp.repositories.psychologists.exceptions import (
    PsychologistNotFoundException
)
from psychohelp.services.psychologist_statuses import (
    set_status,
    delete_status,
    get_psychologist_statuses_service,
    get_current_status_service
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/therapists",
    tags=["therapists Statuses"],
)

@router.post(
    "/{user_id}/statuses",
    response_model=PsychologistStatusResponse,
    summary="Установить статус психолога",
    description=(
        "Устанавливает статус психолога на указанный период и возвращает его данные. user_id — ID "
        "пользователя психолога; требуется право управления психологами или редактирования "
        "собственного профиля."
    ),
)
async def set_psychologist_status(
    user_id: UUID,
    status_request: PsychologistStatusCreateRequest,
    current_user: User = Depends(get_current_user)
):
    """Устанавливает статус психолога на указанный период."""
    is_manage_allowed = await user_has_permission(current_user.id, PermissionCode.PSYCHOLOGISTS_MANAGE)

    is_edit_own_allowed = await user_has_permission(current_user.id, PermissionCode.PSYCHOLOGISTS_EDIT_OWN_PROFILE)
    
    if not is_manage_allowed:
        if not is_edit_own_allowed or current_user.id != user_id:
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для установки статуса психолога"
            )
    
    try:
        new_status = await set_status(
            psychologist_id=user_id,
            start_date=status_request.start_date,
            end_date=status_request.end_date,
            status=status_request.status
        )

        return new_status
    
    except OverlappingStatusException as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Психолог с ID {e.psychologist_id} имеет пересекающийся статус"
        )
    
    except InvalidStatusPeriodException as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Психолог с ID {e.psychologist_id} имеет недопустимый период статуса"
        )
    
    except PsychologistNotFoundException as e:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Психолог с ID {e.psychologist_id} не найден"
        )

@router.delete(
    "/{user_id}/statuses/{status_id}",
    summary="Удалить статус психолога",
    description=(
        "Удаляет статус по status_id для психолога с указанным user_id. Требуется право "
        "управления психологами или редактирования собственного профиля."
    ),
)
async def delete_psychologist_status(
    user_id: UUID,
    status_id: UUID,
    current_user: User = Depends(get_current_user)
):
    """Удаляет статус психолога по его user_id психолога и ID статуса."""
    is_manage_allowed = await user_has_permission(current_user.id, PermissionCode.PSYCHOLOGISTS_MANAGE)

    is_edit_own_allowed = await user_has_permission(current_user.id, PermissionCode.PSYCHOLOGISTS_EDIT_OWN_PROFILE)

    if not is_manage_allowed:
        if not is_edit_own_allowed or current_user.id != user_id:
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для удаления статуса психолога"
            )
    
    try:
        result = await delete_status(status_id, user_id)

        if not result:
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Не удалось удалить статус психолога"
            )
        
        return {"message": "Статус психолога успешно удален"}
    except PsychologistStatusNotFound as e:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Статус с ID {e.status_id} не найден"
        )

@router.get(
    "/{user_id}/statuses",
    response_model=list[PsychologistStatusResponse],
    summary="Получить статусы психолога",
    description=(
        "Возвращает все периоды статусов психолога по ID его пользователя. Требуется право "
        "управления психологами или редактирования собственного профиля."
    ),
)
async def get_psychologist_statuses(
    user_id: UUID,
    current_user: User = Depends(get_current_user)
):
    """Получает все статусы психолога по его ID."""
    is_manage_allowed = await user_has_permission(current_user.id, PermissionCode.PSYCHOLOGISTS_MANAGE)

    is_edit_own_allowed = await user_has_permission(current_user.id, PermissionCode.PSYCHOLOGISTS_EDIT_OWN_PROFILE)

    if not is_manage_allowed:
        if not is_edit_own_allowed or current_user.id != user_id:
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для просмотра статусов психолога"
            )
        
    try:
        statuses = await get_psychologist_statuses_service(user_id)
        return statuses
    except PsychologistNotFoundException as e:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Психолог с ID {e.psychologist_id} не найден"
        )

@router.get(
    "/{user_id}/statuses/current",
    response_model=CurrentStatusInfoResponse,
    summary="Получить текущий статус психолога",
    description=(
        "Возвращает текущий статус психолога по ID его пользователя и сведения о периоде статуса. "
        "Если действующего статуса нет, возвращает available; авторизация не требуется."
    ),
)
async def get_psychologist_current_status(
    user_id: UUID
):
    """Получает текущий статус психолога по ID психолога"""
    try:
        status = await get_current_status_service(user_id)
        return status
    
    except UserIsNotPsychologist as e:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=f"Пользователь с ID {e.user_id} не является психологом"
        )
