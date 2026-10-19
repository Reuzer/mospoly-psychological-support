from fastapi import HTTPException, Security
from fastapi.security import APIKeyCookie
from starlette.status import HTTP_401_UNAUTHORIZED
from psychohelp.services.users.users import get_user_by_token
from psychohelp.models.users import User
from jwt import InvalidTokenError

access_token_cookie = APIKeyCookie(
    name="access_token", scheme_name="cookieAuth", auto_error=False,
    description="JWT авторизованного пользователя в cookie access_token",
)


async def get_current_user(
    access_token: str | None = Security(access_token_cookie),
) -> User:
    """Dependency для получения текущего пользователя из токена"""
    token = access_token
    if not token:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED, 
            detail="Пользователь не авторизован"
        )
    
    try:
        user = await get_user_by_token(token)
    except (InvalidTokenError, ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Недействительный или истекший токен",
        )
    if user is None:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED, 
            detail="Пользователь не авторизован"
        )
    
    return user


async def get_optional_user(
    access_token: str | None = Security(access_token_cookie),
) -> User | None:
    """Dependency для опционального получения пользователя (если токен есть)"""
    token = access_token
    if not token:
        return None
    
    try:
        return await get_user_by_token(token)
    except (InvalidTokenError, ValueError, KeyError, TypeError):
        return None
