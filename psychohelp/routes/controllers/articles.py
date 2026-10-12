from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.status import HTTP_201_CREATED, HTTP_404_NOT_FOUND

from psychohelp.config.logging import get_logger
from psychohelp.constants.rbac import PermissionCode
from psychohelp.dependencies.auth import get_current_user
from psychohelp.models.users import User
from psychohelp.schemas.articles import (
    ArticleCreateRequest,
    ArticleResponse,
    ArticleUpdateRequest,
)
from psychohelp.services import articles as articles_service
from psychohelp.services.rbac.permissions import require_permission


logger = get_logger(__name__)
router = APIRouter(prefix="/articles", tags=["articles"])


@router.get(
    "/",
    response_model=list[ArticleResponse],
    summary="Получить список статей",
    description=(
        "Возвращает список статей с пагинацией: skip задаёт число пропускаемых записей, take — "
        "размер выборки. Авторизация не требуется."
    ),
)
async def get_articles(
    skip: int = Query(0, ge=0, description="Количество записей для пропуска"),
    take: int = Query(100, gt=0, le=100, description="Количество записей для получения"),
) -> list[ArticleResponse]:
    articles = await articles_service.get_articles(skip=skip, take=take)
    return articles


@router.get(
    "/{article_id}",
    response_model=ArticleResponse,
    summary="Получить статью по ID",
    description=(
        "Возвращает данные статьи по её идентификатору. Авторизация не требуется; если статья не "
        "найдена, возвращает 404."
    ),
)
async def get_article(article_id: UUID) -> ArticleResponse:
    article = await articles_service.get_article_by_id(article_id)
    if article is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Статья не найдена")
    return article


@router.post(
    "/",
    response_model=ArticleResponse,
    status_code=HTTP_201_CREATED,
    summary="Создать статью",
    description=(
        "Создаёт статью из переданных данных и возвращает её. Требуется авторизация и право "
        "создания статей."
    ),
)
@require_permission(PermissionCode.ARTICLES_CREATE)
async def create_article(
    data: ArticleCreateRequest,
    current_user: User = Depends(get_current_user),
) -> ArticleResponse:
    article = await articles_service.create_article(data.model_dump())
    logger.info(f"Article created: {article.id}")
    return article


@router.put(
    "/{article_id}",
    response_model=ArticleResponse,
    summary="Обновить статью",
    description=(
        "Обновляет данные статьи по её идентификатору и возвращает результат. Требуется "
        "авторизация и право редактирования статей."
    ),
)
@require_permission(PermissionCode.ARTICLES_EDIT)
async def update_article(
    article_id: UUID,
    data: ArticleUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> ArticleResponse:
    article = await articles_service.update_article(article_id, data.model_dump())
    if article is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Статья не найдена")
    logger.info(f"Article updated: {article_id}")
    return article


@router.delete(
    "/{article_id}",
    summary="Удалить статью",
    description=(
        "Удаляет статью по её идентификатору и возвращает сообщение об удалении. Требуется "
        "авторизация и право удаления статей."
    ),
)
@require_permission(PermissionCode.ARTICLES_DELETE)
async def delete_article(
    article_id: UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    deleted = await articles_service.delete_article(article_id)
    if not deleted:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Статья не найдена")
    logger.info(f"Article deleted: {article_id}")
    return {"message": "Статья успешно удалена"}
