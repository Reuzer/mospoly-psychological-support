from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.status import HTTP_201_CREATED, HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND

from psychohelp.config.logging import get_logger
from psychohelp.constants.rbac import RoleCode
from psychohelp.dependencies.auth import get_current_user
from psychohelp.models.users import User
from psychohelp.schemas.psy_tests import (
    PsyTestCreateRequest,
    PsyTestResponse,
    PsyTestUpdateRequest,
)
import psychohelp.services.psy_tests as psy_test_service


logger = get_logger(__name__)
router = APIRouter(prefix="/psy-tests", tags=["psy-tests"])


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
async def create_psy_test(
    data: PsyTestCreateRequest,
    current_user: User = Depends(get_current_user),
) -> PsyTestResponse:
    _ensure_admin(current_user)
    psy_test_item = await psy_test_service.create_psy_test(data.model_dump())
    logger.info(f"PsyTest created: {psy_test_item.id}")
    return psy_test_item


@router.put("/{psy_test_id}", response_model=PsyTestResponse)
async def update_psy_test(
    psy_test_id: UUID,
    data: PsyTestUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> PsyTestResponse:
    _ensure_admin(current_user)
    psy_test_item = await psy_test_service.update_psy_test(psy_test_id, data.model_dump())
    if psy_test_item is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Тест не найден")
    logger.info(f"PsyTest updated: {psy_test_id}")
    return psy_test_item


@router.delete("/{psy_test_id}")
async def delete_psy_test(
    psy_test_id: UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    _ensure_admin(current_user)
    deleted = await psy_test_service.delete_psy_test(psy_test_id)
    if not deleted:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Тест не найден")
    logger.info(f"PsyTest deleted: {psy_test_id}")
    return {"message": "Тест успешно удален"}