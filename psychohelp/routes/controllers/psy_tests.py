from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.status import HTTP_201_CREATED, HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND

from psychohelp.config.logging import get_logger
from psychohelp.constants.rbac import PermissionCode
from psychohelp.dependencies.auth import get_current_user
from psychohelp.models.users import User
from psychohelp.schemas.psy_tests import (
    PsyTestCreateRequest,
    PsyTestResponse,
    PsyTestUpdateRequest,
)
import psychohelp.services.psy_tests as psy_test_service
from psychohelp.services.rbac.permissions import require_permission


logger = get_logger(__name__)
router = APIRouter(prefix="/psy-tests", tags=["psy-tests"])


@router.get("/", response_model=list[PsyTestResponse])
async def get_psy_test_list(
    skip: int = Query(0, ge=0, description="Количество записей для пропуска"),
    take: int = Query(100, gt=0, le=100, description="Количество записей для получения"),
) -> list[PsyTestResponse]:
    psy_test_list = await psy_test_service.get_psy_test_list(skip=skip, take=take)
    return psy_test_list


@router.get("/{psy_test_id}", response_model=PsyTestResponse)
async def get_psy_test(psy_test_id: UUID) -> PsyTestResponse:
    psy_test_item = await psy_test_service.get_psy_test_by_id(psy_test_id)
    if psy_test_item is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Тест не найден")
    return psy_test_item


@router.post("/", response_model=PsyTestResponse, status_code=HTTP_201_CREATED)
@require_permission(PermissionCode.TESTS_CREATE)
async def create_psy_test(
    data: PsyTestCreateRequest,
    current_user: User = Depends(get_current_user),
) -> PsyTestResponse:
    psy_test_item = await psy_test_service.create_psy_test(data.model_dump())
    logger.info(f"PsyTest created: {psy_test_item.id}")
    return psy_test_item


@router.put("/{psy_test_id}", response_model=PsyTestResponse)
@require_permission(PermissionCode.TESTS_EDIT)
async def update_psy_test(
    psy_test_id: UUID,
    data: PsyTestUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> PsyTestResponse:
    psy_test_item = await psy_test_service.update_psy_test(
        psy_test_id,
        data.model_dump(exclude_unset=True, exclude_none=True)) # игнорирует поля, которые не прислали
    if psy_test_item is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Тест не найден")
    logger.info(f"PsyTest updated: {psy_test_id}")
    return psy_test_item


@router.delete("/{psy_test_id}")
@require_permission(PermissionCode.TESTS_DELETE)
async def delete_psy_test(
    psy_test_id: UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    deleted = await psy_test_service.delete_psy_test(psy_test_id)
    if not deleted:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Тест не найден")
    logger.info(f"PsyTest deleted: {psy_test_id}")
    return {"message": "Тест успешно удален"}