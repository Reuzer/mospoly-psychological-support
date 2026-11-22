from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from starlette.status import HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND, HTTP_409_CONFLICT

from psychohelp.constants.rbac import RoleCode
from psychohelp.dependencies.auth import get_current_user
from psychohelp.models.users import User
from psychohelp.schemas.errors import error_responses
from psychohelp.schemas.medical_records import (
    MedicalRecordNoteResponse,
    MedicalRecordNoteUpdateRequest,
    MedicalRecordPreview,
    MedicalRecordResponse,
)
from psychohelp.services import medical_records as service
from psychohelp.services.medical_record_exceptions import (
    MedicalRecordNotFoundException,
    MedicalRecordNoteVersionConflict,
)


async def get_medical_record_staff(
    current_user: User = Depends(get_current_user),
) -> User:
    """Медкарты доступны только психологам и администраторам."""
    if not any(
        role.code in (RoleCode.PSYCHOLOGIST, RoleCode.ADMIN)
        for role in (current_user.roles or [])
    ):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Медкарты доступны только психологам и администраторам",
        )
    return current_user


router = APIRouter(
    prefix="/medical-records", tags=["medical-records"],
    dependencies=[Depends(get_medical_record_staff)],
)


@router.get(
    "/", response_model=list[MedicalRecordPreview], responses=error_responses(401, 403),
)
async def get_medical_record_list() -> list[MedicalRecordPreview]:
    """Возвращает по одной карточке на пользователя с ролью обучающегося."""
    return await service.get_medical_record_list()


@router.get(
    "/{user_id}", response_model=MedicalRecordResponse,
    responses=error_responses(401, 403, 404),
)
async def get_medical_record(user_id: UUID) -> MedicalRecordResponse:
    """Возвращает профиль пациента, общую заметку и историю завершённых приёмов."""
    try:
        return await service.get_medical_record_by_user_id(user_id)
    except MedicalRecordNotFoundException as exc:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=str(exc))


@router.patch(
    "/{user_id}/note", response_model=MedicalRecordNoteResponse,
    responses=error_responses(401, 403, 404, 409),
)
async def update_medical_record_note(
    user_id: UUID, data: MedicalRecordNoteUpdateRequest,
) -> MedicalRecordNoteResponse:
    """Сохраняет общую заметку, если её версия не изменилась с момента чтения."""
    try:
        return await service.update_medical_record_note(user_id, **data.model_dump())
    except MedicalRecordNotFoundException as exc:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=str(exc))
    except MedicalRecordNoteVersionConflict as exc:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(exc))
