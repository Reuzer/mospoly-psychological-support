from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.exc import SQLAlchemyError
from starlette.status import HTTP_201_CREATED, HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND

from psychohelp.schemas.errors import error_responses
from psychohelp.config.logging import get_logger
from psychohelp.constants.rbac import PermissionCode, RoleCode
from psychohelp.dependencies.auth import get_current_user
from psychohelp.models.psy_tests import PsyTestQuestion, TestType
from psychohelp.models.users import User
from psychohelp.routes.psy_test_route import PsyTestRoute
from psychohelp.schemas.psy_tests import (
    PsyTestCreateRequest,
    PsyTestListItem,
    PsyTestQuestionResponse,
    PsyTestResponse,
    PsyTestUpdateRequest,
)
import psychohelp.services.psy_tests as psy_test_service
from psychohelp.repositories import psy_tests as psy_test_repository
from psychohelp.services.psy_test_images import IMAGE_FILENAME, IMAGE_URL_PREFIX
from psychohelp.services.rbac import permissions


logger = get_logger(__name__)
router = APIRouter(prefix="/psy-tests", tags=["psy-tests"], route_class=PsyTestRoute)


async def _require_write_permission(current_user: User, test_type: TestType, permission: PermissionCode):
    if test_type == TestType.MEDICAL:
        if not any(role.code in (RoleCode.PSYCHOLOGIST, RoleCode.ADMIN) for role in current_user.roles):
            raise HTTPException(HTTP_403_FORBIDDEN, "Медицинские тесты редактируют психологи и администраторы")
    elif not await permissions.user_has_permission(current_user.id, permission):
        raise HTTPException(HTTP_403_FORBIDDEN, f"Недостаточно прав: требуется {permission.value}")


async def _require_test_write(psy_test_id: UUID, current_user: User, permission: PermissionCode):
    test = await psy_test_service.get_psy_test_by_id(psy_test_id)
    if test is None:
        raise HTTPException(HTTP_404_NOT_FOUND, "Тест не найден")
    await _require_write_permission(current_user, test.type, permission)


async def _require_medical_test_staff(current_user: User = Depends(get_current_user)):
    await _require_write_permission(current_user, TestType.MEDICAL, PermissionCode.TESTS_EDIT)


def _image_root_path(image: str | None, root_path: str, *, add: bool) -> str | None:
    """Учитываем префикс API для загруженных фото, сохраняя старые и внешние ссылки"""
    prefix = IMAGE_URL_PREFIX if add else root_path + IMAGE_URL_PREFIX
    if image and image.startswith(prefix) and IMAGE_FILENAME.fullmatch(image.removeprefix(prefix)):
        return root_path + image if add else image.removeprefix(root_path)
    return image


def _psy_test_response(psy_test_item, request: Request | None) -> PsyTestResponse:
    response = PsyTestResponse.model_validate(psy_test_item)
    root_path = request.scope.get("root_path", "").rstrip("/") if request else ""
    if root_path:
        response.image = _image_root_path(response.image, root_path, add=True)
    return response


def _psy_test_data(data: dict, request: Request | None) -> dict:
    root_path = request.scope.get("root_path", "").rstrip("/") if request else ""
    if root_path and "image" in data:
        data["image"] = _image_root_path(data["image"], root_path, add=False)
    if data.get("url") is not None:
        data["url"] = str(data["url"])
    return data


def question_response(question: PsyTestQuestion, request: Request) -> PsyTestQuestionResponse:
    response = PsyTestQuestionResponse.model_validate(question)
    root_path = request.scope.get("root_path", "").rstrip("/")
    if root_path:
        response.image = _image_root_path(response.image, root_path, add=True)
    return response


@router.get("/", response_model=list[PsyTestListItem])
async def get_psy_test_list(
    skip: int = Query(0, ge=0, description="Количество записей для пропуска"),
    take: int = Query(100, gt=0, le=100, description="Количество записей для получения"),
    request: Request = None,
) -> list[PsyTestListItem]:
    psy_test_list = await psy_test_service.get_psy_test_list(skip=skip, take=take)
    return [
        PsyTestListItem(**_psy_test_response(item, request).model_dump(), questions_count=count)
        for item, count in psy_test_list
    ]


@router.get("/{psy_test_id}", responses=error_responses(404), response_model=PsyTestResponse)
async def get_psy_test(psy_test_id: UUID, request: Request = None) -> PsyTestResponse:
    psy_test_item = await psy_test_service.get_psy_test_by_id(psy_test_id)
    if psy_test_item is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Тест не найден")
    return _psy_test_response(psy_test_item, request)


@router.post("/", responses=error_responses(401, 403), response_model=PsyTestResponse, status_code=HTTP_201_CREATED)
async def create_psy_test(
    data: PsyTestCreateRequest,
    current_user: User = Depends(get_current_user),
    request: Request = None,
) -> PsyTestResponse:
    await _require_write_permission(current_user, data.type, PermissionCode.TESTS_CREATE)
    psy_test_item = await psy_test_service.create_psy_test(_psy_test_data(data.model_dump(), request))
    logger.info(f"PsyTest created: {psy_test_item.id}")
    return _psy_test_response(psy_test_item, request)


@router.put("/{psy_test_id}", responses=error_responses(401, 403, 404, 409), response_model=PsyTestResponse)
async def update_psy_test(
    psy_test_id: UUID,
    data: PsyTestUpdateRequest,
    current_user: User = Depends(get_current_user),
    request: Request = None,
) -> PsyTestResponse:
    await _require_test_write(psy_test_id, current_user, PermissionCode.TESTS_EDIT)
    # Игнорируем поля, которые не прислали, и null для обязательных полей.
    update_data = {
        field: value
        for field, value in data.model_dump(exclude_unset=True).items()
        if value is not None or field in {"image", "url", "estimated_duration_minutes"}
    }
    psy_test_item = await psy_test_service.update_psy_test(
        psy_test_id, _psy_test_data(update_data, request),
    )
    if psy_test_item is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Тест не найден")
    logger.info(f"PsyTest updated: {psy_test_id}")
    return _psy_test_response(psy_test_item, request)


@router.delete("/{psy_test_id}", responses=error_responses(401, 403, 404))
async def delete_psy_test(
    psy_test_id: UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    await _require_test_write(psy_test_id, current_user, PermissionCode.TESTS_DELETE)
    deleted = await psy_test_service.delete_psy_test(psy_test_id)
    if not deleted:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Тест не найден")
    logger.info(f"PsyTest deleted: {psy_test_id}")
    return {"message": "Тест успешно удален"}


@router.post(
    "/{psy_test_id}/image",
    responses=error_responses(400, 401, 403, 404, 413, 415, 500),
    response_model=PsyTestResponse,
    summary="Загрузить или заменить фотографию теста",
    description="JPEG, PNG или WebP до 10 МБ и 20 млн пикселей, без анимации.",
)
async def upload_psy_test_image(
    psy_test_id: UUID,
    image: UploadFile = File(..., description="Фотография теста (JPEG, PNG или WebP)"),
    current_user: User = Depends(get_current_user),
    request: Request = None,
) -> PsyTestResponse:
    await _require_test_write(psy_test_id, current_user, PermissionCode.TESTS_EDIT)
    try:
        psy_test_item = await psy_test_service.upload_psy_test_image(psy_test_id, image)
    except SQLAlchemyError as exc:
        logger.exception("Could not persist psy test image: %s", psy_test_id)
        raise HTTPException(500, "Не удалось сохранить фотографию") from exc
    if psy_test_item is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Тест не найден")
    logger.info("PsyTest image updated: %s", psy_test_id)
    return _psy_test_response(psy_test_item, request)


@router.delete(
    "/{psy_test_id}/image",
    responses=error_responses(401, 403, 404),
    response_model=PsyTestResponse,
    summary="Удалить фотографию теста",
)
async def delete_psy_test_image(
    psy_test_id: UUID,
    current_user: User = Depends(get_current_user),
    request: Request = None,
) -> PsyTestResponse:
    await _require_test_write(psy_test_id, current_user, PermissionCode.TESTS_EDIT)
    psy_test_item = await psy_test_service.update_psy_test(psy_test_id, {"image": None})
    if psy_test_item is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Тест не найден")
    logger.info("PsyTest image removed: %s", psy_test_id)
    return _psy_test_response(psy_test_item, request)


@router.get(
    "/{psy_test_id}/questions", response_model=list[PsyTestQuestionResponse],
    dependencies=[Depends(_require_medical_test_staff)], responses=error_responses(401, 403, 404),
)
async def get_medical_test_questions(psy_test_id: UUID, request: Request) -> list[PsyTestQuestionResponse]:
    """Показывает психологу или администратору вопросы в порядке прохождения."""
    questions = await psy_test_repository.list_medical_test_questions(psy_test_id)
    return [question_response(question, request) for question in questions]


@router.post(
    "/{psy_test_id}/questions/{question_id}/image", response_model=PsyTestQuestionResponse,
    dependencies=[Depends(_require_medical_test_staff)],
    responses=error_responses(400, 401, 403, 404, 409, 413, 415, 500),
)
async def upload_medical_test_question_image(
    psy_test_id: UUID, question_id: UUID, request: Request, image: UploadFile = File(...),
) -> PsyTestQuestionResponse:
    """Прикрепляет изображение в формате JPEG, PNG или WebP до 10 МБ."""
    try:
        question = await psy_test_service.upload_medical_test_question_image(psy_test_id, question_id, image)
    except SQLAlchemyError as exc:
        logger.exception("Could not persist psy test question image: %s", question_id)
        raise HTTPException(500, "Не удалось сохранить фотографию") from exc
    return question_response(question, request)


@router.delete(
    "/{psy_test_id}/questions/{question_id}/image", response_model=PsyTestQuestionResponse,
    dependencies=[Depends(_require_medical_test_staff)], responses=error_responses(401, 403, 404, 409),
)
async def delete_medical_test_question_image(
    psy_test_id: UUID, question_id: UUID, request: Request,
) -> PsyTestQuestionResponse:
    """Удаляет изображение вопроса до начала прохождений."""
    question = await psy_test_service.update_medical_test_question_image(psy_test_id, question_id, None)
    return question_response(question, request)
