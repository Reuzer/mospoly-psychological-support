from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.exc import SQLAlchemyError
from starlette.status import HTTP_201_CREATED, HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND

from psychohelp.schemas.errors import error_responses
from psychohelp.config.logging import get_logger
from psychohelp.constants.rbac import RoleCode
from psychohelp.dependencies.auth import get_current_user
from psychohelp.models.users import User
from psychohelp.routes.upload_limits import ImageUploadRoute
from psychohelp.schemas.news import (
    NewsCreateRequest,
    NewsResponse,
    NewsUpdateRequest,
)
from psychohelp.services import news as news_service
from psychohelp.services.news_images import IMAGE_FILENAME, IMAGE_URL_PREFIX


logger = get_logger(__name__)
router = APIRouter(prefix="/news", tags=["news"], route_class=ImageUploadRoute)


def _image_root_path(image: str | None, root_path: str, *, add: bool) -> str | None:
    prefix = IMAGE_URL_PREFIX if add else root_path + IMAGE_URL_PREFIX
    if image and image.startswith(prefix) and IMAGE_FILENAME.fullmatch(image.removeprefix(prefix)):
        return root_path + image if add else image.removeprefix(root_path)
    return image


def _news_response(news_item, request: Request | None):
    root_path = request.scope.get("root_path", "").rstrip("/") if request else ""
    if not root_path:
        return news_item
    response = NewsResponse.model_validate(news_item)
    response.image = _image_root_path(response.image, root_path, add=True)
    return response


def _news_data(data: dict, request: Request | None) -> dict:
    root_path = request.scope.get("root_path", "").rstrip("/") if request else ""
    if root_path and "image" in data:
        data["image"] = _image_root_path(data["image"], root_path, add=False)
    return data


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


@router.get("/", response_model=list[NewsResponse])
async def get_news_list(
    skip: int = Query(0, ge=0, description="Количество записей для пропуска"),
    take: int = Query(100, gt=0, le=100, description="Количество записей для получения"),
    request: Request = None,
) -> list[NewsResponse]:
    news_list = await news_service.get_news_list(skip=skip, take=take)
    return [_news_response(news_item, request) for news_item in news_list]


@router.get("/{news_id}", responses=error_responses(404), response_model=NewsResponse)
async def get_news(news_id: UUID, request: Request = None) -> NewsResponse:
    news_item = await news_service.get_news_by_id(news_id)
    if news_item is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Новость не найдена")
    return _news_response(news_item, request)


@router.post("/", responses=error_responses(401, 403), response_model=NewsResponse, status_code=HTTP_201_CREATED)
async def create_news(
    data: NewsCreateRequest,
    current_user: User = Depends(get_current_user),
    request: Request = None,
) -> NewsResponse:
    _ensure_admin(current_user)
    news_item = await news_service.create_news(_news_data(data.model_dump(), request))
    logger.info(f"News created: {news_item.id}")
    return _news_response(news_item, request)


@router.put("/{news_id}", responses=error_responses(401, 403, 404), response_model=NewsResponse)
async def update_news(
    news_id: UUID,
    data: NewsUpdateRequest,
    current_user: User = Depends(get_current_user),
    request: Request = None,
) -> NewsResponse:
    _ensure_admin(current_user)
    news_item = await news_service.update_news(
        news_id, _news_data(data.model_dump(exclude_unset=True), request)
    )
    if news_item is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Новость не найдена")
    logger.info(f"News updated: {news_id}")
    return _news_response(news_item, request)


@router.delete("/{news_id}", responses=error_responses(401, 403, 404))
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


@router.post(
    "/{news_id}/image",
    responses=error_responses(400, 401, 403, 404, 413, 415, 500),
    response_model=NewsResponse,
    summary="Загрузить или заменить фотографию новости",
    description="JPG/JPEG, PNG или WebP до 10 МиБ и 20 млн пикселей, без анимации. Только для администраторов.",
)
async def upload_news_image(
    news_id: UUID,
    image: UploadFile = File(..., description="Фотография новости (JPG/JPEG, PNG или WebP)"),
    current_user: User = Depends(get_current_user),
    request: Request = None,
) -> NewsResponse:
    _ensure_admin(current_user)
    try:
        news_item = await news_service.upload_news_image(news_id, image)
    except SQLAlchemyError as exc:
        logger.exception("Could not persist news image: %s", news_id)
        raise HTTPException(500, "Не удалось сохранить фотографию") from exc
    if news_item is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Новость не найдена")
    logger.info("News image updated: %s", news_id)
    return _news_response(news_item, request)


@router.delete(
    "/{news_id}/image",
    responses=error_responses(401, 403, 404),
    response_model=NewsResponse,
    summary="Удалить фотографию новости",
)
async def delete_news_image(
    news_id: UUID,
    current_user: User = Depends(get_current_user),
    request: Request = None,
) -> NewsResponse:
    _ensure_admin(current_user)
    news_item = await news_service.update_news(news_id, {"image": None})
    if news_item is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Новость не найдена")
    logger.info("News image removed: %s", news_id)
    return _news_response(news_item, request)
