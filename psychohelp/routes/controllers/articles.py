from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.exc import SQLAlchemyError
from starlette.status import HTTP_201_CREATED, HTTP_404_NOT_FOUND

from psychohelp.schemas.errors import error_responses
from psychohelp.config.logging import get_logger
from psychohelp.constants.rbac import PermissionCode
from psychohelp.dependencies.auth import get_current_user
from psychohelp.models.users import User
from psychohelp.routes.upload_limits import ArticleImageUploadRoute
from psychohelp.schemas.articles import (
    ArticleCreateRequest,
    ArticleResponse,
    ArticleUpdateRequest,
)
from psychohelp.services import articles as articles_service
from psychohelp.services.article_images import IMAGE_FILENAME, IMAGE_URL_PREFIX
from psychohelp.services.rbac.permissions import require_permission


logger = get_logger(__name__)
router = APIRouter(prefix="/articles", tags=["articles"], route_class=ArticleImageUploadRoute)


def _image_root_path(image: str | None, root_path: str, *, add: bool) -> str | None:
    """Учитываем префикс API для загруженных фото, сохраняя старые и внешние ссылки"""
    prefix = IMAGE_URL_PREFIX if add else root_path + IMAGE_URL_PREFIX
    if image and image.startswith(prefix) and IMAGE_FILENAME.fullmatch(image.removeprefix(prefix)):
        return root_path + image if add else image.removeprefix(root_path)
    return image


def _article_response(article, request: Request | None):
    root_path = request.scope.get("root_path", "").rstrip("/") if request else ""
    if not root_path:
        return article
    response = ArticleResponse.model_validate(article)
    response.image = _image_root_path(response.image, root_path, add=True)
    return response


def _article_data(data: dict, request: Request | None) -> dict:
    root_path = request.scope.get("root_path", "").rstrip("/") if request else ""
    if root_path and "image" in data:
        data["image"] = _image_root_path(data["image"], root_path, add=False)
    return data


@router.get("/", response_model=list[ArticleResponse])
async def get_articles(
    skip: int = Query(0, ge=0, description="Количество записей для пропуска"),
    take: int = Query(100, gt=0, le=100, description="Количество записей для получения"),
    request: Request = None,
) -> list[ArticleResponse]:
    articles = await articles_service.get_articles(skip=skip, take=take)
    return [_article_response(article, request) for article in articles]


@router.get("/{article_id}", responses=error_responses(404), response_model=ArticleResponse)
async def get_article(article_id: UUID, request: Request = None) -> ArticleResponse:
    article = await articles_service.get_article_by_id(article_id)
    if article is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Статья не найдена")
    return _article_response(article, request)


@router.post("/", responses=error_responses(401, 403), response_model=ArticleResponse, status_code=HTTP_201_CREATED)
@require_permission(PermissionCode.ARTICLES_CREATE)
async def create_article(
    data: ArticleCreateRequest,
    current_user: User = Depends(get_current_user),
    request: Request = None,
) -> ArticleResponse:
    article = await articles_service.create_article(_article_data(data.model_dump(), request))
    logger.info(f"Article created: {article.id}")
    return _article_response(article, request)


@router.put("/{article_id}", responses=error_responses(401, 403, 404), response_model=ArticleResponse)
@require_permission(PermissionCode.ARTICLES_EDIT)
async def update_article(
    article_id: UUID,
    data: ArticleUpdateRequest,
    current_user: User = Depends(get_current_user),
    request: Request = None,
) -> ArticleResponse:
    article = await articles_service.update_article(
        article_id, _article_data(data.model_dump(exclude_unset=True), request)
    )
    if article is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Статья не найдена")
    logger.info(f"Article updated: {article_id}")
    return _article_response(article, request)


@router.delete("/{article_id}", responses=error_responses(401, 403, 404))
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


@router.post(
    "/{article_id}/image",
    responses=error_responses(400, 401, 403, 404, 413, 415, 500),
    response_model=ArticleResponse,
    summary="Загрузить или заменить фотографию статьи",
    description="JPEG, PNG или WebP до 10 МБ и 20 млн пикселей, без анимации. Требуется articles.edit.",
)
@require_permission(PermissionCode.ARTICLES_EDIT)
async def upload_article_image(
    article_id: UUID,
    image: UploadFile = File(..., description="Фотография статьи (JPEG, PNG или WebP)"),
    current_user: User = Depends(get_current_user),
    request: Request = None,
) -> ArticleResponse:
    try:
        article = await articles_service.upload_article_image(article_id, image)
    except SQLAlchemyError as exc:
        logger.exception("Could not persist article image: %s", article_id)
        raise HTTPException(500, "Не удалось сохранить фотографию") from exc
    if article is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Статья не найдена")
    logger.info("Article image updated: %s", article_id)
    return _article_response(article, request)


@router.delete(
    "/{article_id}/image",
    responses=error_responses(401, 403, 404),
    response_model=ArticleResponse,
    summary="Удалить фотографию статьи",
)
@require_permission(PermissionCode.ARTICLES_EDIT)
async def delete_article_image(
    article_id: UUID,
    current_user: User = Depends(get_current_user),
    request: Request = None,
) -> ArticleResponse:
    article = await articles_service.update_article(article_id, {"image": None})
    if article is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Статья не найдена")
    logger.info("Article image removed: %s", article_id)
    return _article_response(article, request)
