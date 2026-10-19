from uuid import UUID

from fastapi import HTTPException, APIRouter, Query, Request, Depends
from starlette.status import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from psychohelp.schemas.errors import error_responses
from psychohelp.config.logging import get_logger
from psychohelp.services.psychologists import (
    get_psychologist_by_id,
    get_psychologists as srv_get_psychologists,
    create_psychologist,
    delete_psychologist,
)
from psychohelp.repositories.psychologists.exceptions import (
    UserNotFoundForPsychologistException,
    PsychologistRoleNotFoundException,
    PsychologistAlreadyExistsException,
)
from psychohelp.schemas.psychologists import PsychologistResponse, PsychologistCreateRequest
from psychohelp.services.rbac.permissions import require_permission, user_has_permission
from psychohelp.constants.rbac import PermissionCode, RoleCode
from psychohelp.dependencies.auth import get_current_user
from psychohelp.models.users import User

logger = get_logger(__name__)
router = APIRouter(prefix="/therapists", tags=["therapists"])


@router.get("/{psychologist_id}", responses=error_responses(404), response_model=PsychologistResponse)
async def get_psychologist(psychologist_id: UUID) -> PsychologistResponse:
    """Получить информацию о конкретном психологе по ID"""
    psychologist = await get_psychologist_by_id(psychologist_id)
    if psychologist is None:
        logger.warning(f"Psychologist not found: {psychologist_id}")
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Psychologist not found")
    
    logger.info(f"Psychologist retrieved: {psychologist_id}")
    return PsychologistResponse.from_orm_psychologist(psychologist)


@router.get("/", response_model=list[PsychologistResponse])
async def get_psychologists(
    skip: int = Query(0, ge=0, description="Количество записей для пропуска"),
    take: int = Query(10, gt=0, le=100, description="Количество записей для получения")
) -> list[PsychologistResponse]:
    """Получить список всех психологов с пагинацией"""
    logger.info(f"Fetching psychologists: skip={skip}, take={take}")
    psychologists = await srv_get_psychologists(skip=skip, take=take)
    
    logger.info(f"Retrieved {len(psychologists)} psychologists")
    return [PsychologistResponse.from_orm_psychologist(p) for p in psychologists]


@router.post("/", responses=error_responses(400, 401, 403, 404, 500), response_model=PsychologistResponse, status_code=HTTP_201_CREATED)
async def create_psychologist_endpoint(
    request: Request,
    data: PsychologistCreateRequest,
    current_user: User = Depends(get_current_user),
) -> PsychologistResponse:
    try:
        role_codes = {role.code for role in current_user.roles}
        is_manage_allowed = await user_has_permission(
            current_user.id, PermissionCode.PSYCHOLOGISTS_MANAGE
        )
        is_psychologist = RoleCode.PSYCHOLOGIST in role_codes

        if not is_manage_allowed:
            if not is_psychologist or data.user_id != current_user.id:
                raise HTTPException(
                    status_code=HTTP_403_FORBIDDEN,
                    detail=f"Недостаточно прав: требуется {PermissionCode.PSYCHOLOGISTS_MANAGE.value}",
                )

        psychologist_data = data.model_dump(exclude={"user_id"})
        psychologist = await create_psychologist(data.user_id, psychologist_data)
        logger.info(f"Psychologist created: {psychologist.id} for user {data.user_id}")
        return PsychologistResponse.from_orm_psychologist(psychologist)
    
    except UserNotFoundForPsychologistException as e:
        logger.error(f"User not found: {data.user_id}")
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=str(e))
    
    except PsychologistRoleNotFoundException as e:
        logger.error("Psychologist role not found in database")
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    except PsychologistAlreadyExistsException as e:
        logger.warning(f"Psychologist already exists for user: {data.user_id}")
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{psychologist_id}", responses=error_responses(401, 403, 404))
@require_permission(PermissionCode.PSYCHOLOGISTS_MANAGE)
async def delete_psychologist_endpoint(request: Request, psychologist_id: UUID) -> dict[str, str]:
    deleted = await delete_psychologist(psychologist_id)
    if not deleted:
        logger.warning(f"Psychologist not found for deletion: {psychologist_id}")
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Psychologist not found")
    
    logger.info(f"Psychologist deleted: {psychologist_id}")
    return {"message": "Psychologist successfully deleted"}

