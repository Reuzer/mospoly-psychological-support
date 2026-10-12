from fastapi import HTTPException, APIRouter, Depends, Request, Response
from jwt.exceptions import PyJWTError

from starlette.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_401_UNAUTHORIZED,
    HTTP_404_NOT_FOUND,
    HTTP_422_UNPROCESSABLE_ENTITY, 
    HTTP_403_FORBIDDEN,
    HTTP_500_INTERNAL_SERVER_ERROR,
)
from pydantic import EmailStr, BaseModel

from typing import Optional

from psychohelp.config.logging import get_logger
from psychohelp.services.users import users
from psychohelp.models.users import User
from psychohelp.services.users import exceptions as users_exceptions

from psychohelp.schemas.users import (
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PsychologistPublicCard,
    UserCreateRequest,
    UserResponse,
)
from . import set_token_in_cookie, set_refresh_token_in_cookie

from starlette.status import HTTP_400_BAD_REQUEST, HTTP_409_CONFLICT
from uuid import UUID
from psychohelp.schemas.users import UserUpdateRequest, PasswordChangeRequest
from psychohelp.services.email import EmailDeliveryError
from psychohelp.services.users.password_reset import (
    InvalidPasswordResetToken,
    request_password_reset,
    reset_password,
)
from psychohelp.services.users.users import update_profile, change_password
from psychohelp.services.users.exceptions import PermissionDenied, UserNotFound
from psychohelp.constants.rbac import PermissionCode, RoleCode
from psychohelp.dependencies.auth import get_current_user, get_optional_user
from psychohelp.services.rbac.permissions import user_has_permission

logger = get_logger(__name__)
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/users", tags=["users"])


@router.get("/user", response_model=UserResponse)
async def user_token(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return current_user


@router.get("/user/{id}", response_model=UserResponse | PsychologistPublicCard)
async def user(
    id: users.UUID,
    current_user: User | None = Depends(get_optional_user),
) -> UserResponse | PsychologistPublicCard:
    """Полный профиль — самому пользователю или сотруднику с users.view_all.
    Остальным доступна только публичная карточка психолога."""
    user = await users.get_user_by_id(id)
    if user is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail="Пользователь не найден"
        )

    if current_user is not None and (
        current_user.id == user.id
        or await user_has_permission(current_user.id, PermissionCode.USERS_VIEW_ALL)
    ):
        return UserResponse.model_validate(user)

    if any(role.code == RoleCode.PSYCHOLOGIST for role in user.roles):
        return PsychologistPublicCard.model_validate(user)

    if current_user is None:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован"
        )
    raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Доступ запрещен")


@router.post("/register", response_model=UserResponse, status_code=HTTP_201_CREATED)
async def register_users(user_data: UserCreateRequest, response: Response) -> UserResponse:
    try:
        user, token, refresh_token = await users.register_user(**user_data.model_dump())
        set_token_in_cookie(response, token)
        set_refresh_token_in_cookie(response, refresh_token)
        response.status_code = HTTP_201_CREATED
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return user


@router.post("/login", response_model=UserResponse)
@limiter.limit("5/minute")
async def login(request: Request, data: LoginRequest, response: Response) -> UserResponse:
    try:
        user_with_token = await users.login_user(data.email, data.password)
        user = user_with_token.user
        token = user_with_token.token
        refresh_token = user_with_token.refresh_token

        set_token_in_cookie(response, token)
        set_refresh_token_in_cookie(response, refresh_token)
        response.status_code = HTTP_200_OK
        return user
    except (users_exceptions.UserNotFound, users_exceptions.WrongPassword):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED, detail="Неверные данные"
    )


@router.post("/logout")
async def logout(response: Response) -> Response:
    response.status_code = HTTP_200_OK
    response.delete_cookie("access_token", secure=False, samesite="Lax")
    response.delete_cookie("refresh_token", secure=False, samesite="Lax")
    return response


@router.post("/refresh", response_model=UserResponse)
async def refresh_token(request: Request, response: Response) -> UserResponse:
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token is None:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED, detail="Пользователь не авторизован"
        )
    try:
        new_access_token = users.refresh_access_token(refresh_token)
        user = await users.get_user_by_token(new_access_token)
        if user is None:
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="Недействительный токен обновления",
            )
        set_token_in_cookie(response, new_access_token)
        response.status_code = HTTP_200_OK
        return user
    except (users_exceptions.InvalidToken, PyJWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED, detail="Недействительный токен обновления"
        )


@router.post("/password-reset/request", status_code=HTTP_200_OK)
@limiter.limit("5/minute")
async def request_password_reset_email(
    request: Request,
    data: PasswordResetRequest,
) -> dict[str, str]:
    try:
        message = await request_password_reset(data.email)
    except EmailDeliveryError:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось отправить письмо для восстановления пароля",
        )
    return {"message": message}


@router.post("/password-reset/confirm", status_code=HTTP_200_OK)
@limiter.limit("10/minute")
async def confirm_password_reset(
    request: Request,
    data: PasswordResetConfirmRequest,
) -> dict[str, str]:
    try:
        await reset_password(data.token, data.new_password)
    except InvalidPasswordResetToken:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Недействительная или истекшая ссылка восстановления пароля",
        )
    return {"message": "Пароль успешно изменён"}


@router.put("/me", response_model=UserResponse)
async def update_my_profile(
    data: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Обновление своего профиля (требуется авторизация)"""
    try:
        updated_user = await update_profile(
            current_user_id=current_user.id,
            target_user_id=current_user.id,
            data=data,
            is_admin=False
        )
    except UserNotFound:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )
    except PermissionDenied as e:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Неожиданная ошибка при обновлении профиля: {e}", exc_info=True)
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервера"
        )

    if updated_user is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    return UserResponse.model_validate(updated_user)


class UserStatusResponse(BaseModel):
    status: Optional[str] = None


@router.get("/me/status", response_model=UserStatusResponse, summary="Получить статус обучающегося")
async def get_my_status(
    request: Request,
    current_user: User = Depends(get_current_user)
) -> UserStatusResponse:
    user_status = getattr(current_user, "group_status", None)
    if hasattr(user_status, "value"):
        user_status = user_status.value

    return UserStatusResponse.model_validate(user_status)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user_by_id(
    user_id: UUID,
    data: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Обновление профиля любого пользователя (только для администраторов)"""
    is_admin = any(
        role.code == RoleCode.ADMIN for role in (current_user.roles or [])
    )
    if not is_admin:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Доступ запрещен. Только для администраторов."
        )

    try:
        updated_user = await update_profile(
            current_user_id=current_user.id,
            target_user_id=user_id,
            data=data,
            is_admin=True
        )
    except UserNotFound:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )
    except PermissionDenied as e:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except HTTPException as e:
        raise e

    if updated_user is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    return UserResponse.model_validate(updated_user)


@router.post("/me/password", status_code=HTTP_200_OK)
async def change_my_password(
    data: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Смена пароля текущего пользователя"""
    try:
        await change_password(current_user.id, data.old_password, data.new_password)
    except UserNotFound:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    return {"message": "Пароль успешно изменён"}