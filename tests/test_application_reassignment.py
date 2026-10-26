from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError as SchemaValidationError

from psychohelp.constants.rbac import RoleCode
from psychohelp.dependencies.auth import get_current_user
from psychohelp.models.applications import ApplicationStatus
from psychohelp.routes.controllers import applications as applications_controller
from psychohelp.schemas.applications import ApplicationReassignRequest
from psychohelp.services.applications import applications as applications_service
from psychohelp.services.applications.exceptions import (
    AccessDeniedError,
    ApplicationNotFoundError,
    ConflictError,
    InvalidStatusTransitionError,
    ValidationError,
)


def _user(name, role=RoleCode.USER):
    return SimpleNamespace(
        id=uuid4(),
        first_name=name,
        middle_name=None,
        last_name="Пользователь",
        phone_number="+79991234567",
        email=f"{uuid4().hex}@example.com",
        social_media=None,
        study_group=None,
        roles=[SimpleNamespace(code=role)],
    )


def _psychologist(user, office):
    return SimpleNamespace(
        id=uuid4(),
        user_id=user.id,
        user=user,
        experience="5 лет",
        qualification="Психолог",
        consult_areas="Стресс",
        description="Описание",
        office=office,
        education="Высшее",
        short_description="Психолог",
        photo=None,
    )


@pytest.fixture
def reassignment(monkeypatch):
    now = datetime.now(timezone.utc)
    patient = _user("Пациент")
    previous_user = _user("Прежний", RoleCode.PSYCHOLOGIST)
    actor = _user("Новый", RoleCode.PSYCHOLOGIST)
    previous_psychologist = _psychologist(previous_user, "Старый кабинет")
    psychologist = _psychologist(actor, "Новый кабинет")
    application = SimpleNamespace(
        id=uuid4(),
        user_id=patient.id,
        user=patient,
        assigned_to=previous_user.id,
        assigned_to_user=previous_user,
        psychologist_id=previous_psychologist.id,
        psychologist=previous_psychologist,
        appointment_id=None,
        appointment=None,
        problem_description="Нужна психологическая консультация",
        preferred_campus="Большая Семеновская",
        university_status="студент",
        status=ApplicationStatus.AWAITING_USER_CONFIRMATION.value,
        meeting_type="offline",
        scheduled_at=now + timedelta(days=2),
        location_address="Согласованный адрес",
        meeting_url=None,
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=1),
        processing_started_at=now - timedelta(days=1),
        confirmation_requested_at=now - timedelta(hours=1),
        completed_at=None,
        rejected_at=None,
        cancelled_at=None,
        expired_at=None,
        reject_reason=None,
        cancel_reason=None,
        cancel_initiator=None,
        internal_comment=None,
        version=3,
    )
    state = SimpleNamespace(
        actor=actor,
        psychologist=psychologist,
        application=application,
        user_exists=True,
        profile_exists=True,
        application_exists=True,
        available=True,
        conflict=False,
        writes=[],
        availability_checks=[],
    )

    async def get_user(user_id):
        assert user_id == actor.id
        return actor if state.user_exists else None

    async def get_psychologist(user_id):
        assert user_id == actor.id
        return psychologist if state.profile_exists else None

    async def get_application(application_id):
        assert application_id == application.id
        return application if state.application_exists else None

    async def check_availability(psychologist_id, scheduled_time):
        state.availability_checks.append((psychologist_id, scheduled_time))
        return state.available

    async def update_application(application_id, expected_version, payload):
        assert application_id == application.id
        state.writes.append((expected_version, dict(payload)))
        if state.conflict or expected_version != application.version:
            return None
        for field, value in payload.items():
            setattr(application, field, value)
        application.version += 1
        application.assigned_to_user = actor
        application.psychologist = psychologist
        return application

    monkeypatch.setattr(applications_service, "get_user_by_id", get_user)
    monkeypatch.setattr(applications_service, "get_psychologist_by_user_id", get_psychologist)
    monkeypatch.setattr(applications_service, "check_psychologist_availability", check_availability)
    monkeypatch.setattr(applications_service.repo, "get_application_by_id", get_application)
    monkeypatch.setattr(applications_service.repo, "update_application_with_version", update_application)
    return state


async def _reassign(state, payload=None):
    return await applications_service.reassign_application(
        state.application.id,
        ApplicationReassignRequest.model_validate(payload or {}),
        state.actor.id,
    )


@pytest.mark.asyncio
async def test_another_psychologist_takes_application_and_preserves_omitted_terms(reassignment):
    state = reassignment
    previous_time = state.application.scheduled_at
    previous_confirmation = state.application.confirmation_requested_at

    result = await _reassign(state)

    assert result.user_id != state.actor.id
    assert result.psychologist_id == state.psychologist.id
    assert result.assigned_to == state.actor.id
    assert result.status == ApplicationStatus.AWAITING_USER_CONFIRMATION.value
    assert result.scheduled_at == previous_time
    assert result.location_address == "Согласованный адрес"
    assert result.appointment_id is None
    assert result.completed_at is None
    assert result.confirmation_requested_at > previous_confirmation
    assert result.version == 4
    assert state.writes[0][0] == 3
    assert state.availability_checks == [(state.psychologist.id, previous_time)]


@pytest.mark.asyncio
async def test_repeated_change_of_terms_still_requires_patient_confirmation(reassignment):
    state = reassignment
    first_time = datetime.now(timezone.utc) + timedelta(days=4)
    second_time = first_time + timedelta(days=1)

    await _reassign(state, {"scheduled_at": first_time, "location_address": "Кабинет 101"})
    result = await _reassign(state, {"scheduled_at": second_time})

    assert result.scheduled_at == second_time
    assert result.location_address == "Кабинет 101"
    assert result.status == ApplicationStatus.AWAITING_USER_CONFIRMATION.value
    assert result.version == 5
    assert [expected_version for expected_version, _ in state.writes] == [3, 4]


@pytest.mark.asyncio
async def test_online_reassignment_preserves_omitted_meeting_url(reassignment):
    state = reassignment
    state.application.meeting_type = "online"
    state.application.location_address = None
    state.application.meeting_url = "https://example.com/shared-meeting"

    result = await _reassign(state)

    assert result.meeting_type == "online"
    assert result.meeting_url == "https://example.com/shared-meeting"
    assert result.location_address is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("old_type", "payload", "expected_type", "expected_address", "expected_url"),
    [
        (
            "offline",
            {"meeting_type": "online", "meeting_url": "https://example.com/new-meeting"},
            "online",
            None,
            "https://example.com/new-meeting",
        ),
        (
            "online",
            {"meeting_type": "offline", "location_address": "Другой кабинет"},
            "offline",
            "Другой кабинет",
            None,
        ),
    ],
)
async def test_switching_format_clears_previous_format_details(
    reassignment, old_type, payload, expected_type, expected_address, expected_url
):
    state = reassignment
    state.application.meeting_type = old_type
    state.application.location_address = "Старый кабинет" if old_type == "offline" else None
    state.application.meeting_url = "https://example.com/old-meeting" if old_type == "online" else None

    result = await _reassign(state, payload)

    assert result.meeting_type == expected_type
    assert result.location_address == expected_address
    assert result.meeting_url == expected_url


@pytest.mark.asyncio
@pytest.mark.parametrize("old_type", ["offline", "online"])
async def test_switching_format_requires_the_new_format_details(reassignment, old_type):
    state = reassignment
    state.application.meeting_type = old_type
    state.application.location_address = "Адрес" if old_type == "offline" else None
    state.application.meeting_url = "https://example.com/meeting" if old_type == "online" else None
    new_type = "online" if old_type == "offline" else "offline"

    with pytest.raises(ValidationError):
        await _reassign(state, {"meeting_type": new_type})

    assert state.writes == []


@pytest.mark.asyncio
async def test_reassignment_normalizes_new_time_before_availability_check(reassignment):
    state = reassignment
    local_timezone = timezone(timedelta(hours=3))
    new_time = (datetime.now(timezone.utc) + timedelta(days=3)).astimezone(local_timezone)

    result = await _reassign(state, {"scheduled_at": new_time})

    assert result.scheduled_at == new_time
    assert result.scheduled_at.tzinfo == timezone.utc
    assert state.availability_checks == [(state.psychologist.id, new_time.astimezone(timezone.utc))]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [RoleCode.USER, RoleCode.ADMIN, RoleCode.CONTENT_MANAGER])
async def test_non_psychologist_roles_cannot_take_application(reassignment, role):
    state = reassignment
    state.actor.roles = [SimpleNamespace(code=role)]

    with pytest.raises(AccessDeniedError):
        await _reassign(state)

    assert state.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_attribute", ["user_exists", "profile_exists"])
async def test_role_or_authenticated_id_without_real_profile_is_not_enough(reassignment, missing_attribute):
    state = reassignment
    setattr(state, missing_attribute, False)

    with pytest.raises(AccessDeniedError):
        await _reassign(state)

    assert state.writes == []


@pytest.mark.asyncio
async def test_missing_application_is_not_written(reassignment):
    state = reassignment
    state.application_exists = False

    with pytest.raises(ApplicationNotFoundError):
        await _reassign(state)

    assert state.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [status for status in ApplicationStatus if status != ApplicationStatus.AWAITING_USER_CONFIRMATION],
)
async def test_only_applications_awaiting_confirmation_can_be_reassigned(reassignment, status):
    state = reassignment
    state.application.status = status.value

    with pytest.raises(InvalidStatusTransitionError):
        await _reassign(state)

    assert state.writes == []


@pytest.mark.asyncio
async def test_unavailable_psychologist_cannot_take_application(reassignment):
    state = reassignment
    state.available = False

    with pytest.raises(ValidationError):
        await _reassign(state)

    assert state.writes == []
    assert state.application.assigned_to != state.actor.id


@pytest.mark.asyncio
async def test_stale_application_version_does_not_replace_assignment(reassignment):
    state = reassignment
    state.conflict = True
    old_psychologist = state.application.psychologist_id

    with pytest.raises(ConflictError):
        await _reassign(state)

    assert state.application.psychologist_id == old_psychologist
    assert state.application.version == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_terms", ["past_time", "online_without_url", "offline_without_address"])
async def test_invalid_effective_terms_are_rejected_even_when_omitted_from_body(reassignment, invalid_terms):
    state = reassignment
    if invalid_terms == "past_time":
        state.application.scheduled_at = datetime.now(timezone.utc) - timedelta(hours=1)
    elif invalid_terms == "online_without_url":
        state.application.meeting_type = "online"
        state.application.location_address = None
        state.application.meeting_url = None
    else:
        state.application.location_address = None

    with pytest.raises(ValidationError):
        await _reassign(state)

    assert state.writes == []


@pytest.mark.asyncio
async def test_partial_update_cannot_clear_required_offline_address(reassignment):
    state = reassignment

    with pytest.raises(ValidationError):
        await _reassign(state, {"location_address": None})

    assert state.writes == []


@pytest.mark.asyncio
async def test_partial_update_can_clear_irrelevant_meeting_url(reassignment):
    state = reassignment
    state.application.meeting_url = "https://example.com/obsolete"

    result = await _reassign(state, {"meeting_url": None})

    assert result.location_address == "Согласованный адрес"
    assert result.meeting_url is None


@pytest.mark.parametrize(
    "payload",
    [
        {"psychologist_id": str(uuid4())},
        {"assigned_to": str(uuid4())},
        {"meeting_type": None},
        {"scheduled_at": None},
        {"location_address": ""},
        {"location_address": "   "},
        {"meeting_url": ""},
        {"meeting_url": "   "},
        {"meeting_url": "x" * 513},
    ],
)
def test_partial_request_rejects_target_ids_and_invalid_values(payload):
    with pytest.raises(SchemaValidationError):
        ApplicationReassignRequest.model_validate(payload)


def _app(state=None):
    app = FastAPI()
    app.include_router(applications_controller.router)
    if state is not None:
        async def current_user():
            return state.actor

        app.dependency_overrides[get_current_user] = current_user
    return app


@pytest.mark.asyncio
async def test_http_reassignment_without_authentication_returns_401():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://test") as client:
        response = await client.post(f"/applications/{uuid4()}/reassign", json={})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_http_reassignment_requires_an_explicit_body(reassignment):
    state = reassignment
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app(state)), base_url="http://test") as client:
        response = await client.post(f"/applications/{state.application.id}/reassign")

    assert response.status_code == 422
    assert state.writes == []


@pytest.mark.asyncio
async def test_http_reassignment_uses_current_actor_and_returns_updated_nested_profile(reassignment):
    state = reassignment
    new_time = datetime.now(timezone.utc) + timedelta(days=5)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app(state)), base_url="http://test") as client:
        response = await client.post(
            f"/applications/{state.application.id}/reassign",
            json={"scheduled_at": new_time.isoformat()},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["psychologist"]["id"] == str(state.psychologist.id)
    assert data["assigned_to_user"]["id"] == str(state.actor.id)
    assert data["user"]["id"] != str(state.actor.id)
    assert data["status"] == "awaiting_user_confirmation"
    assert data["version"] == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        ("non_psychologist", 403),
        ("missing_profile", 403),
        ("missing_application", 404),
        ("completed", 409),
        ("version_conflict", 409),
        ("unavailable", 400),
        ("past_time", 400),
        ("missing_address", 400),
    ],
)
async def test_http_reassignment_maps_business_failures(reassignment, failure, expected_status):
    state = reassignment
    if failure == "non_psychologist":
        state.actor.roles = [SimpleNamespace(code=RoleCode.USER)]
    elif failure == "missing_profile":
        state.profile_exists = False
    elif failure == "missing_application":
        state.application_exists = False
    elif failure == "completed":
        state.application.status = ApplicationStatus.COMPLETED.value
    elif failure == "version_conflict":
        state.conflict = True
    elif failure == "unavailable":
        state.available = False
    elif failure == "missing_address":
        state.application.location_address = None
    else:
        state.application.scheduled_at = datetime.now(timezone.utc) - timedelta(hours=1)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app(state)), base_url="http://test") as client:
        response = await client.post(f"/applications/{state.application.id}/reassign", json={})

    assert response.status_code == expected_status
    assert response.json()["detail"]
    if failure != "version_conflict":
        assert state.writes == []


@pytest.mark.asyncio
async def test_http_reassignment_cannot_target_another_psychologist(reassignment):
    state = reassignment
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app(state)), base_url="http://test") as client:
        response = await client.post(
            f"/applications/{state.application.id}/reassign",
            json={"psychologist_id": str(uuid4())},
        )

    assert response.status_code == 422
    assert state.writes == []


@pytest.mark.parametrize("payload", [{"meeting_url": "x" * 129}, {"location_address": "x" * 129}])
def test_reassignment_limits_venue_to_appointment_storage_length(payload):
    with pytest.raises(SchemaValidationError):
        ApplicationReassignRequest.model_validate(payload)


async def test_legacy_long_address_cannot_be_offered_again(reassignment):
    reassignment.application.location_address = "x" * 129
    with pytest.raises(ValidationError, match="128"):
        await _reassign(reassignment)
    assert reassignment.writes == []
