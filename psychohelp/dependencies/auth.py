from fastapi import HTTPException, Security
from fastapi.security import APIKeyCookie
from jwt.exceptions import PyJWTError
from starlette.status import HTTP_401_UNAUTHORIZED

from psychohelp.models.users import User
from psychohelp.services.users.users import get_user_by_token

access_token_cookie = APIKeyCookie(
    name="access_token", scheme_name="cookieAuth", auto_error=False,
    description="JWT авторизованного пользователя в cookie access_token",
)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=HTTP_401_UNAUTHORIZED,
        detail="Пользователь не авторизован",
    )


async def get_current_user(
    access_token: str | None = Security(access_token_cookie),
) -> User:
    """Dependency для получения текущего пользователя из токена"""
    if not access_token:
        raise _unauthorized()

    try:
        user = await get_user_by_token(access_token)
    except (PyJWTError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Недействительный или просроченный токен",
        )

    if user is None:
        raise _unauthorized()

    return user


async def get_optional_user(
    access_token: str | None = Security(access_token_cookie),
) -> User | None:
    """Dependency для опционального получения пользователя (если токен есть)"""
    if not access_token:
        return None

    try:
        user = await get_user_by_token(access_token)
    except (PyJWTError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Недействительный или просроченный токен",
        )

    if user is None:
        raise _unauthorized()

    return user
