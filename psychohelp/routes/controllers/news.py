from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.status import HTTP_201_CREATED, HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND

from psychohelp.config.logging import get_logger
from psychohelp.constants.rbac import RoleCode
from psychohelp.dependencies.auth import get_current_user
from psychohelp.models.users import User
from psychohelp.schemas.news import (
    NewsCreateRequest,
    NewsResponse,
    NewsUpdateRequest,
)
from psychohelp.services import news as news_service


logger = get_logger(__name__)
router = APIRouter(prefix="/news", tags=["news"])


def _ensure_admin(user: User) -> None:
    role_codes = {
        getattr(getattr(role, "code", role), "value", getattr(role, "code", role))
        for role in (user.roles or [])
    }
    if RoleCode.ADMIN.value not in role_codes:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Доступ запрещен. Только для администраторов.",
        )


@router.get(
    "/",
    response_model=list[NewsResponse],
    summary="Получить список новостей",
    description=(
        "Возвращает список новостей с пагинацией: skip задаёт число пропускаемых записей, take — "
        "размер выборки. Авторизация не требуется."
    ),
)
async def get_news_list(
    skip: int = Query(0, ge=0, description="Количество записей для пропуска"),
    take: int = Query(100, gt=0, le=100, description="Количество записей для получения"),
) -> list[NewsResponse]:
    news_list = await news_service.get_news_list(skip=skip, take=take)
    return news_list


@router.get(
    "/{news_id}",
    response_model=NewsResponse,
    summary="Получить новость по ID",
    description=(
        "Возвращает данные новости по её идентификатору. Авторизация не требуется; если новость "
        "не найдена, возвращает 404."
    ),
)
async def get_news(news_id: UUID) -> NewsResponse:
    news_item = await news_service.get_news_by_id(news_id)
    if news_item is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Новость не найдена")
    return news_item


@router.post(
    "/",
    response_model=NewsResponse,
    status_code=HTTP_201_CREATED,
    summary="Создать новость",
    description=(
        "Создаёт новость из переданных данных и возвращает её. Доступно только авторизованному "
        "администратору."
    ),
)
async def create_news(
    data: NewsCreateRequest,
    current_user: User = Depends(get_current_user),
) -> NewsResponse:
    _ensure_admin(current_user)
    news_item = await news_service.create_news(data.model_dump())
    logger.info(f"News created: {news_item.id}")
    return news_item


@router.put(
    "/{news_id}",
    response_model=NewsResponse,
    summary="Обновить новость",
    description=(
        "Обновляет данные новости по её идентификатору и возвращает результат. Доступно только "
        "авторизованному администратору."
    ),
)
async def update_news(
    news_id: UUID,
    data: NewsUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> NewsResponse:
    _ensure_admin(current_user)
    news_item = await news_service.update_news(news_id, data.model_dump())
    if news_item is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Новость не найдена")
    logger.info(f"News updated: {news_id}")
    return news_item


@router.delete(
    "/{news_id}",
    summary="Удалить новость",
    description=(
        "Удаляет новость по её идентификатору и возвращает сообщение об удалении. Доступно только "
        "авторизованному администратору."
    ),
)
async def delete_news(
    news_id: UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    _ensure_admin(current_user)
    deleted = await news_service.delete_news(news_id)
    if not deleted:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Новость не найдена")
    logger.info(f"News deleted: {news_id}")
    return {"message": "Новость успешно удалена"}
