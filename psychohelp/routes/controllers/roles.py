from uuid import UUID

from fastapi import HTTPException, APIRouter, Request

from starlette.status import (
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN
)

from psychohelp.config.logging import get_logger
from psychohelp.repositories.rbac.rbac import (
    assign_role_to_user,
    remove_role_from_user,
)
from psychohelp.repositories.rbac.exceptions import (
    UserNotFoundException,
    RoleNotFoundException,
)
from psychohelp.schemas.roles import RoleAssignRequest, RoleRemoveRequest

from psychohelp.constants.rbac import RoleCode
from psychohelp.repositories import get_user_id_from_token
from psychohelp.services.users import users

logger = get_logger(__name__)
router = APIRouter(prefix="/roles", tags=["roles"])


def _has_role(user, role_code: RoleCode) -> bool:
    return any(role.code == role_code for role in (user.roles or []))


@router.post(
    "/{user_id}/assign",
    summary="Назначить роль пользователю",
    description=(
        "Назначает указанную роль пользователю по его ID. Доступно только администратору; если "
        "роль уже назначена, сообщает об этом без повторного назначения."
    ),
)
async def assign_role(request: Request, user_id: UUID, role_request: RoleAssignRequest) -> dict[str, str]:
    """Назначить роль пользователю"""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Не авторизован")

    try:
        current_user_id = get_user_id_from_token(token)
    except Exception:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Недействительный токен")

    current_user = await users.get_user_by_id(current_user_id)
    if not current_user or not _has_role(current_user, RoleCode.ADMIN):
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Только для администраторов")

    try:
        assigned = await assign_role_to_user(user_id, role_request.role_code)
        if not assigned:
            logger.info(f"Role '{role_request.role_code.value}' already assigned to user {user_id}")
            return {"message": f"Роль '{role_request.role_code.value}' уже назначена пользователю"}
        logger.info(f"Role '{role_request.role_code.value}' successfully assigned to user {user_id}")
        return {"message": f"Роль '{role_request.role_code.value}' успешно назначена"}

    except (UserNotFoundException, RoleNotFoundException) as e:
        logger.warning(f"Failed to assign role: {str(e)}")
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=str(e))

    except Exception as e:
        logger.exception(
            f"Unexpected error assigning role '{role_request.role_code.value}' to user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось назначить роль"
        )


@router.post(
    "/{user_id}/remove",
    summary="Снять роль с пользователя",
    description=(
        "Снимает указанную роль с пользователя по его ID и возвращает сообщение о результате. "
        "Доступно только администратору."
    ),
)
async def remove_role(request: Request, user_id: UUID, role_request: RoleRemoveRequest) -> dict[str, str]:
    """Убрать роль у пользователя"""

    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Не авторизован")

    try:
        current_user_id = get_user_id_from_token(token)
    except Exception:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Недействительный токен")

    current_user = await users.get_user_by_id(current_user_id)
    if not current_user or not _has_role(current_user, RoleCode.ADMIN):
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Только для администраторов")

    try:
        removed = await remove_role_from_user(user_id, role_request.role_code)
        if not removed:
            logger.info(f"Role '{role_request.role_code.value}' was not assigned to user {user_id}")
            return {"message": f"Роль '{role_request.role_code.value}' не была назначена пользователю"}
        logger.info(f"Role '{role_request.role_code.value}' successfully removed from user {user_id}")
        return {"message": f"Роль '{role_request.role_code.value}' успешно удалена"}

    except UserNotFoundException as e:
        logger.warning(f"Failed to remove role: {str(e)}")
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=str(e))

    except Exception as e:
        logger.exception(
            f"Unexpected error removing role '{role_request.role_code.value}' from user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось удалить роль"
        )
