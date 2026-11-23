from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from psychohelp.constants.rbac import RoleCode
from psychohelp.dependencies.auth import get_current_user
from psychohelp.models.users import User
from psychohelp.repositories import psy_test_attempts as attempts
from psychohelp.routes.controllers.psy_tests import question_response
from psychohelp.routes.psy_test_route import PsyTestRoute
from psychohelp.schemas.errors import error_responses
from psychohelp.schemas.psy_tests import PsyTestAnswerRequest, PsyTestAttemptResponse, PsyTestAttemptSummary


async def _get_student(response: Response, current_user: User = Depends(get_current_user)) -> User:
    if not any(role.code == RoleCode.USER for role in current_user.roles):
        raise HTTPException(403, "Прохождение тестов доступно обучающимся")
    response.headers["Cache-Control"] = "no-store"
    return current_user


async def _require_psychologist(response: Response, current_user: User = Depends(get_current_user)):
    if not any(role.code == RoleCode.PSYCHOLOGIST for role in current_user.roles):
        raise HTTPException(403, "Ответы студентов доступны психологам")
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/psy-tests", tags=["psy-tests"], route_class=PsyTestRoute)
results_router = APIRouter(
    prefix="/medical-records", tags=["medical-records"], route_class=PsyTestRoute,
    dependencies=[Depends(_require_psychologist)],
)


def _attempt_response(progress: dict, request: Request) -> PsyTestAttemptResponse:
    for saved_answer in progress["answers"]:
        saved_answer["question"] = question_response(saved_answer["question"], request)
    if progress["next_question"] is not None:
        progress["next_question"] = question_response(progress["next_question"], request)
    return PsyTestAttemptResponse.model_validate(progress)


@router.post(
    "/{psy_test_id}/attempts", response_model=PsyTestAttemptResponse,
    responses=error_responses(401, 403, 404, 409),
)
async def start_medical_test(
    psy_test_id: UUID, request: Request, current_user: User = Depends(_get_student),
) -> PsyTestAttemptResponse:
    """Начинает тест или возвращает незавершённое прохождение пользователя."""
    progress = await attempts.start_or_resume_attempt(psy_test_id, current_user.id)
    return _attempt_response(progress, request)


@router.get(
    "/{psy_test_id}/attempts/{attempt_id}", response_model=PsyTestAttemptResponse,
    responses=error_responses(401, 403, 404),
)
async def get_own_medical_test_attempt(
    psy_test_id: UUID, attempt_id: UUID, request: Request, current_user: User = Depends(_get_student),
) -> PsyTestAttemptResponse:
    """Возвращает собственные ответы и следующий вопрос."""
    progress = await attempts.get_attempt(current_user.id, attempt_id, test_id=psy_test_id)
    return _attempt_response(progress, request)


@router.put(
    "/{psy_test_id}/attempts/{attempt_id}/answers/{question_id}", response_model=PsyTestAttemptResponse,
    responses=error_responses(401, 403, 404, 409, 422),
)
async def save_medical_test_answer(
    psy_test_id: UUID, attempt_id: UUID, question_id: UUID, data: PsyTestAnswerRequest,
    request: Request, current_user: User = Depends(_get_student),
) -> PsyTestAttemptResponse:
    """Сохраняет ответ на следующий вопрос или изменяет уже сохранённый ответ до завершения теста."""
    progress = await attempts.save_answer(
        psy_test_id, attempt_id, current_user.id, question_id, **data.model_dump(),
    )
    return _attempt_response(progress, request)


@results_router.get(
    "/{user_id}/test-attempts", response_model=list[PsyTestAttemptSummary],
    responses=error_responses(401, 403),
)
async def get_student_test_attempts(
    user_id: UUID, skip: int = Query(0, ge=0), take: int = Query(100, gt=0, le=100),
) -> list[PsyTestAttemptSummary]:
    """Возвращает завершённые и незавершённые медицинские тесты студента."""
    return await attempts.list_attempts_by_user(user_id, skip, take)


@results_router.get(
    "/{user_id}/test-attempts/{attempt_id}", response_model=PsyTestAttemptResponse,
    responses=error_responses(401, 403, 404),
)
async def get_student_test_answers(
    user_id: UUID, attempt_id: UUID, request: Request,
) -> PsyTestAttemptResponse:
    """Возвращает психологу вопросы и сохранённые ответы студента."""
    return _attempt_response(await attempts.get_attempt(user_id, attempt_id), request)
