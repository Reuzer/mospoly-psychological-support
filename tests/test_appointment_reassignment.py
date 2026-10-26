from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import BooleanClauseList, Grouping

from psychohelp.constants.rbac import RoleCode
from psychohelp.dependencies.auth import get_current_user
from psychohelp.models.applications import Application
from psychohelp.models.appointment_reschedule_requests import (
    AppointmentRescheduleRequest,
    AppointmentRescheduleStatus,
)
from psychohelp.models.appointments import Appointment, AppointmentStatus, AppointmentType
from psychohelp.models.psychologists import Psychologist
from psychohelp.models.psychologist_statuses import PsychologistStatus, PsychologistStatusType
from psychohelp.repositories import appointments as appointments_repo
from psychohelp.routes.controllers import appointments as appointments_controller
from psychohelp.services.appointments import appointments as appointments_service
from psychohelp.services.appointments import exceptions as appointment_exceptions


def make_user(role=RoleCode.PSYCHOLOGIST):
    return SimpleNamespace(
        id=uuid4(),
        first_name="Иван",
        middle_name=None,
        last_name="Иванов",
        phone_number="+79991234567",
        email="user@example.com",
        social_media=None,
        study_group=None,
        roles=[SimpleNamespace(code=role)],
    )


def make_psychologist(user):
    return SimpleNamespace(
        id=uuid4(),
        user_id=user.id,
        user=user,
        experience="5 лет",
        qualification="Психолог",
        consult_areas="Тревожность",
        description="Описание",
        office="Другой кабинет",
        education="Университет",
        short_description="Описание",
        photo=None,
    )


def make_appointment(psychologist=None):
    psychologist = psychologist or make_psychologist(make_user())
    now = datetime.now(timezone.utc)
    patient = make_user(RoleCode.USER)
    return SimpleNamespace(
        id=uuid4(),
        patient=patient,
        patient_id=patient.id,
        psychologist=psychologist,
        psychologist_id=psychologist.id,
        application_id=uuid4(),
        status=AppointmentStatus.awaiting,
        type=AppointmentType.Offline,
        scheduled_time=now + timedelta(days=1),
        remind_time=now + timedelta(hours=23),
        last_change_time=now - timedelta(hours=1),
        venue="Согласованный кабинет",
        comment="Согласованный комментарий",
        reason="Причина",
        emergency_contact="Мама, +79991234567",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [RoleCode.USER, RoleCode.ADMIN, RoleCode.CONTENT_MANAGER, None])
async def test_service_requires_actual_psychologist_role(monkeypatch, role):
    actor = make_user(role) if role is not None else None

    async def get_actor(_actor_id):
        return actor

    async def unexpected_call(*_args, **_kwargs):
        raise AssertionError("Unauthorized actor must not reach profile or mutation")

    monkeypatch.setattr(appointments_service, "get_user_by_id", get_actor)
    monkeypatch.setattr(appointments_service, "get_psychologist_by_user_id", unexpected_call)
    monkeypatch.setattr(appointments_service, "repo_reassign_appointment_to_psychologist", unexpected_call)

    with pytest.raises(PermissionError):
        await appointments_service.reassign_appointment_to_self(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_service_requires_psychologist_profile(monkeypatch):
    actor = make_user()

    async def get_actor(_actor_id):
        return actor

    async def get_profile(_actor_id):
        return None

    async def unexpected_mutation(**_kwargs):
        raise AssertionError("Actor without profile must not reach mutation")

    monkeypatch.setattr(appointments_service, "get_user_by_id", get_actor)
    monkeypatch.setattr(appointments_service, "get_psychologist_by_user_id", get_profile)
    monkeypatch.setattr(appointments_service, "repo_reassign_appointment_to_psychologist", unexpected_mutation)

    with pytest.raises(PermissionError, match="профиль психолога"):
        await appointments_service.reassign_appointment_to_self(uuid4(), actor.id)


@pytest.mark.asyncio
async def test_service_only_delegates_actor_identity(monkeypatch):
    actor = make_user()
    profile = make_psychologist(actor)
    appointment = make_appointment()
    captured = {}

    async def get_actor(actor_id):
        assert actor_id == actor.id
        return actor

    async def get_profile(actor_id):
        assert actor_id == actor.id
        return profile

    async def reassign(**kwargs):
        captured.update(kwargs)
        return appointment

    monkeypatch.setattr(appointments_service, "get_user_by_id", get_actor)
    monkeypatch.setattr(appointments_service, "get_psychologist_by_user_id", get_profile)
    monkeypatch.setattr(appointments_service, "repo_reassign_appointment_to_psychologist", reassign)

    assert await appointments_service.reassign_appointment_to_self(appointment.id, actor.id) is appointment
    assert captured == {"appointment_id": appointment.id, "psychologist_user_id": actor.id}


def make_http_app(actor=None):
    app = FastAPI()
    app.include_router(appointments_controller.router)
    if actor is not None:
        app.dependency_overrides[get_current_user] = lambda: actor
    return app


@pytest.mark.asyncio
async def test_reassignment_http_requires_authentication():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_http_app()), base_url="http://test"
    ) as client:
        response = await client.post(f"/appointments/{uuid4()}/reassign")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_reassignment_http_forbids_admin_without_psychologist_role(monkeypatch):
    async def unexpected_mutation(*_args):
        raise AssertionError("Admin role alone does not authorize self reassignment")

    monkeypatch.setattr(appointments_controller, "reassign_appointment_to_self", unexpected_mutation)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_http_app(make_user(RoleCode.ADMIN))),
        base_url="http://test",
    ) as client:
        response = await client.post(f"/appointments/{uuid4()}/reassign")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_reassignment_http_has_no_target_and_returns_updated_profile(monkeypatch):
    actor = make_user()
    appointment = make_appointment(make_psychologist(actor))
    captured = {}

    async def reassign(appointment_id, actor_id):
        captured.update(appointment_id=appointment_id, actor_id=actor_id)
        return appointment

    monkeypatch.setattr(appointments_controller, "reassign_appointment_to_self", reassign)
    app = make_http_app(actor)
    operation = app.openapi()["paths"]["/appointments/{id}/reassign"]["post"]
    assert "requestBody" not in operation
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(f"/appointments/{appointment.id}/reassign")

    assert response.status_code == 200
    assert captured == {"appointment_id": appointment.id, "actor_id": actor.id}
    assert response.json()["psychologist"]["id"] == str(appointment.psychologist.id)
    assert response.json()["psychologist"]["user_id"] == str(actor.id)
    assert response.json()["venue"] == appointment.venue
    assert response.json()["emergency_contact"] == appointment.emergency_contact


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status"),
    [
        (appointment_exceptions.AppointmentNotFoundException(uuid4()), 404),
        (ValueError("Запись уже завершена"), 409),
        (PermissionError("Профиль отсутствует"), 403),
        (appointment_exceptions.PsychologistUnavailableException(uuid4(), datetime.now(timezone.utc)), 409),
    ],
)
async def test_reassignment_http_maps_domain_errors(monkeypatch, error, status):
    async def reassign(*_args):
        raise error

    monkeypatch.setattr(appointments_controller, "reassign_appointment_to_self", reassign)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_http_app(make_user())), base_url="http://test"
    ) as client:
        response = await client.post(f"/appointments/{uuid4()}/reassign")
    assert response.status_code == status


def matches(expression, row):
    """Evaluate SQL predicates against rows, including both application FK links."""
    if isinstance(expression, Grouping):
        return matches(expression.element, row)
    if isinstance(expression, BooleanClauseList):
        values = [matches(clause, row) for clause in expression.clauses]
        return any(values) if expression.operator is operators.or_ else all(values)
    left = getattr(row, expression.left.name)
    right = expression.right.value
    if expression.operator is operators.in_op:
        return left in right
    return expression.operator(left, right)


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def scalar_one_or_none(self):
        assert len(self.rows) <= 1
        return self.rows[0] if self.rows else None

    def scalar_one(self):
        assert len(self.rows) == 1
        return self.rows[0]

    def scalars(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class FakeTransaction:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self

    async def __aexit__(self, error_type, error, traceback):
        self.session.committed = error_type is None
        self.session.rolled_back = error_type is not None
        return False


class FakeSession:
    def __init__(self, appointment, psychologist, applications=(), requests=(), statuses=(), other_appointments=()):
        self.rows = {
            Appointment: ([appointment] if appointment else []) + list(other_appointments),
            Psychologist: [psychologist] if psychologist else [],
            Application: list(applications),
            AppointmentRescheduleRequest: list(requests),
            PsychologistStatus: list(statuses),
        }
        self.queries = []
        self.committed = False
        self.rolled_back = False
        self.flushed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def begin(self):
        return FakeTransaction(self)

    async def execute(self, query):
        self.queries.append(query)
        entity = query.column_descriptions[0]["entity"]
        return FakeResult([row for row in self.rows[entity] if matches(query.whereclause, row)])

    async def flush(self):
        self.flushed = True


def patch_session(monkeypatch, session):
    monkeypatch.setattr(appointments_repo, "get_async_db", lambda: session)


@pytest.mark.asyncio
async def test_repository_syncs_both_application_links_and_rejects_pending_requests(monkeypatch):
    actor = make_user()
    new_psychologist = make_psychologist(actor)
    appointment = make_appointment()
    old_psychologist = appointment.psychologist
    old_time = appointment.last_change_time
    agreed_fields = {
        name: getattr(appointment, name)
        for name in ("status", "scheduled_time", "remind_time", "venue", "type", "comment", "reason", "emergency_contact")
    }
    applications = [
        SimpleNamespace(id=appointment.application_id, appointment_id=None),
        SimpleNamespace(id=uuid4(), appointment_id=appointment.id),
        SimpleNamespace(id=uuid4(), appointment_id=uuid4()),
    ]
    for application in applications:
        application.psychologist_id = old_psychologist.id
        application.assigned_to = old_psychologist.user_id
        application.version = 3
        application.updated_at = old_time
        application.status = "completed"
    pending = SimpleNamespace(
        appointment_id=appointment.id,
        requested_by_user_id=old_psychologist.user_id,
        status=AppointmentRescheduleStatus.pending,
        rejection_comment=None,
        responded_at=None,
    )
    confirmed = SimpleNamespace(
        appointment_id=appointment.id,
        status=AppointmentRescheduleStatus.confirmed,
        rejection_comment=None,
        responded_at=old_time,
    )
    session = FakeSession(appointment, new_psychologist, applications, [pending, confirmed])
    patch_session(monkeypatch, session)

    result = await appointments_repo.reassign_appointment_to_psychologist(appointment.id, actor.id)

    assert session.committed and session.flushed
    assert result is appointment
    assert result.psychologist is new_psychologist
    assert result.psychologist_id == new_psychologist.id
    assert result.psychologist.user is actor
    assert result.last_change_time > old_time
    for name, value in agreed_fields.items():
        assert getattr(result, name) == value
    for application in applications[:2]:
        assert application.psychologist_id == new_psychologist.id
        assert application.assigned_to == actor.id
        assert application.version == 4
        assert application.updated_at == result.last_change_time
        assert application.status == "completed"
    assert applications[2].psychologist_id == old_psychologist.id
    assert applications[2].version == 3
    assert pending.status == AppointmentRescheduleStatus.rejected
    assert "переназначена" in pending.rejection_comment
    assert pending.responded_at == result.last_change_time
    assert confirmed.status == AppointmentRescheduleStatus.confirmed
    assert confirmed.responded_at == old_time
    assert session.queries[0].column_descriptions[0]["entity"] is Appointment
    assert all(
        query._for_update_arg is not None
        for query in session.queries[:-1]
        if query.column_descriptions[0]["name"] != "id"
    )
    assert session.queries[-1].get_execution_options()["populate_existing"] is True


@pytest.mark.asyncio
async def test_repository_updates_application_with_both_links_only_once(monkeypatch):
    actor = make_user()
    profile = make_psychologist(actor)
    appointment = make_appointment()
    application = SimpleNamespace(
        id=appointment.application_id,
        appointment_id=appointment.id,
        psychologist_id=appointment.psychologist_id,
        assigned_to=appointment.psychologist.user_id,
        updated_at=appointment.last_change_time,
        version=8,
    )
    session = FakeSession(appointment, profile, [application])
    patch_session(monkeypatch, session)

    await appointments_repo.reassign_appointment_to_psychologist(appointment.id, actor.id)

    assert application.version == 9


@pytest.mark.asyncio
async def test_repository_same_psychologist_is_noop_even_with_pending_or_unavailability(monkeypatch):
    actor = make_user()
    psychologist = make_psychologist(actor)
    appointment = make_appointment(psychologist)
    old_time = appointment.last_change_time
    pending = SimpleNamespace(status=AppointmentRescheduleStatus.pending)
    application = SimpleNamespace(version=3, updated_at=old_time)
    session = FakeSession(appointment, psychologist, [application], [pending], [SimpleNamespace()])
    patch_session(monkeypatch, session)

    assert await appointments_repo.reassign_appointment_to_psychologist(appointment.id, actor.id) is appointment

    assert appointment.last_change_time == old_time
    assert application.version == 3
    assert application.updated_at == old_time
    assert pending.status == AppointmentRescheduleStatus.pending
    assert len(session.queries) == 2
    assert session.flushed is False


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [AppointmentStatus.done, AppointmentStatus.cancelled])
async def test_repository_rejects_closed_appointments_without_changes(monkeypatch, status):
    actor = make_user()
    appointment = make_appointment()
    appointment.status = status
    old_psychologist_id = appointment.psychologist_id
    old_time = appointment.last_change_time
    session = FakeSession(appointment, make_psychologist(actor))
    patch_session(monkeypatch, session)

    with pytest.raises(ValueError, match="завершенную или отмененную"):
        await appointments_repo.reassign_appointment_to_psychologist(appointment.id, actor.id)

    assert appointment.psychologist_id == old_psychologist_id
    assert appointment.last_change_time == old_time
    assert session.rolled_back and not session.committed


@pytest.mark.asyncio
async def test_repository_missing_appointment_returns_domain_not_found(monkeypatch):
    actor = make_user()
    session = FakeSession(None, make_psychologist(actor))
    patch_session(monkeypatch, session)

    with pytest.raises(appointment_exceptions.AppointmentNotFoundException):
        await appointments_repo.reassign_appointment_to_psychologist(uuid4(), actor.id)
    assert session.rolled_back


@pytest.mark.asyncio
async def test_repository_rechecks_missing_profile(monkeypatch):
    actor = make_user()
    appointment = make_appointment()
    session = FakeSession(appointment, None)
    patch_session(monkeypatch, session)

    with pytest.raises(PermissionError, match="профиль психолога"):
        await appointments_repo.reassign_appointment_to_psychologist(appointment.id, actor.id)
    assert session.rolled_back


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [PsychologistStatusType.sick, PsychologistStatusType.vacation])
async def test_repository_rejects_unavailable_psychologist_at_appointment_time(monkeypatch, status):
    actor = make_user()
    appointment = make_appointment()
    old_psychologist_id = appointment.psychologist_id
    unavailable = SimpleNamespace(
        pid=actor.id,
        status=status,
        start_date=appointment.scheduled_time,
        end_date=appointment.scheduled_time + timedelta(days=1),
    )
    session = FakeSession(appointment, make_psychologist(actor), statuses=[unavailable])
    patch_session(monkeypatch, session)

    with pytest.raises(appointment_exceptions.PsychologistUnavailableException):
        await appointments_repo.reassign_appointment_to_psychologist(appointment.id, actor.id)

    assert appointment.psychologist_id == old_psychologist_id
    assert session.rolled_back and not session.flushed


@pytest.mark.asyncio
async def test_repository_ignores_other_psychologist_and_other_time_unavailability(monkeypatch):
    actor = make_user()
    appointment = make_appointment()
    profile = make_psychologist(actor)
    statuses = [
        SimpleNamespace(
            pid=uuid4(), status=PsychologistStatusType.sick,
            start_date=appointment.scheduled_time, end_date=appointment.scheduled_time,
        ),
        SimpleNamespace(
            pid=actor.id, status=PsychologistStatusType.vacation,
            start_date=appointment.scheduled_time + timedelta(days=1),
            end_date=appointment.scheduled_time + timedelta(days=2),
        ),
    ]
    session = FakeSession(appointment, profile, statuses=statuses)
    patch_session(monkeypatch, session)

    await appointments_repo.reassign_appointment_to_psychologist(appointment.id, actor.id)
    assert session.committed
    assert appointment.psychologist_id == profile.id


@pytest.mark.parametrize("time_zone", [timezone.utc, timezone(timedelta(hours=3))])
async def test_repository_rejects_busy_psychologist_without_changing_related_data(monkeypatch, time_zone):
    actor = make_user()
    profile = make_psychologist(actor)
    appointment = make_appointment()
    other = make_appointment(profile)
    other.scheduled_time = appointment.scheduled_time.astimezone(time_zone)
    application = SimpleNamespace(
        id=appointment.application_id, appointment_id=appointment.id,
        psychologist_id=appointment.psychologist_id,
        assigned_to=appointment.psychologist.user_id,
        version=3, updated_at=appointment.last_change_time,
    )
    pending = SimpleNamespace(
        appointment_id=appointment.id, status=AppointmentRescheduleStatus.pending,
        rejection_comment=None, responded_at=None,
    )
    objects = (appointment, other, application, pending)
    snapshots = [vars(obj).copy() for obj in objects]
    session = FakeSession(appointment, profile, [application], [pending], other_appointments=[other])
    patch_session(monkeypatch, session)

    with pytest.raises(appointment_exceptions.PsychologistUnavailableException) as error:
        await appointments_repo.reassign_appointment_to_psychologist(appointment.id, actor.id)

    assert error.value.psychologist_id == profile.id
    assert error.value.scheduled_time == appointment.scheduled_time
    assert [vars(obj) for obj in objects] == snapshots
    assert session.rolled_back and not session.committed and not session.flushed


@pytest.mark.parametrize("difference", ["psychologist", "time", "done", "cancelled"])
async def test_repository_ignores_appointments_that_do_not_occupy_target_slot(monkeypatch, difference):
    actor = make_user()
    profile = make_psychologist(actor)
    appointment = make_appointment()
    other = make_appointment(profile)
    other.scheduled_time = appointment.scheduled_time
    if difference == "psychologist":
        other.psychologist_id = appointment.psychologist_id
    elif difference == "time":
        other.scheduled_time += timedelta(hours=2)
    else:
        other.status = AppointmentStatus(difference)
    snapshot = vars(other).copy()
    session = FakeSession(appointment, profile, other_appointments=[other])
    patch_session(monkeypatch, session)

    result = await appointments_repo.reassign_appointment_to_psychologist(appointment.id, actor.id)

    assert result.psychologist_id == profile.id
    assert session.committed and session.flushed
    assert vars(other) == snapshot


async def test_http_busy_psychologist_returns_409_without_side_effects(monkeypatch):
    from unittest.mock import AsyncMock

    actor = make_user()
    profile = make_psychologist(actor)
    appointment = make_appointment()
    other = make_appointment(profile)
    other.scheduled_time = appointment.scheduled_time
    snapshots = [vars(obj).copy() for obj in (appointment, other)]
    session = FakeSession(appointment, profile, other_appointments=[other])
    patch_session(monkeypatch, session)
    monkeypatch.setattr(appointments_service, "get_user_by_id", AsyncMock(return_value=actor))
    monkeypatch.setattr(appointments_service, "get_psychologist_by_user_id", AsyncMock(return_value=profile))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_http_app(actor)), base_url="http://test",
    ) as client:
        response = await client.post(f"/appointments/{appointment.id}/reassign")

    assert response.status_code == 409
    assert "недоступен" in response.json()["detail"]
    assert [vars(obj) for obj in (appointment, other)] == snapshots
    assert session.rolled_back and not session.flushed


@pytest.mark.parametrize("same_psychologist", [False, True])
@pytest.mark.parametrize("offset_seconds", [-1, 0])
@pytest.mark.parametrize("time_zone", [timezone.utc, timezone(timedelta(hours=3)), timezone(timedelta(hours=-5)), None])
async def test_elapsed_appointments_cannot_be_reassigned_even_by_current_psychologist(
    monkeypatch, same_psychologist, offset_seconds, time_zone,
):
    now = datetime.now(timezone.utc)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz else now.replace(tzinfo=None)

    monkeypatch.setattr(appointments_repo, "datetime", FrozenDatetime)
    actor = make_user()
    profile = make_psychologist(actor)
    appointment = make_appointment(profile if same_psychologist else None)
    scheduled = now + timedelta(seconds=offset_seconds)
    appointment.scheduled_time = scheduled.astimezone(time_zone) if time_zone else scheduled.replace(tzinfo=None)
    snapshot = vars(appointment).copy()
    application = SimpleNamespace(version=3)
    pending = SimpleNamespace(status=AppointmentRescheduleStatus.pending)
    session = FakeSession(appointment, profile, [application], [pending])
    patch_session(monkeypatch, session)

    with pytest.raises(ValueError, match="время которой уже наступило"):
        await appointments_repo.reassign_appointment_to_psychologist(appointment.id, actor.id)

    assert vars(appointment) == snapshot
    assert application.version == 3
    assert pending.status == AppointmentRescheduleStatus.pending
    assert session.rolled_back and not session.committed and not session.flushed


@pytest.mark.parametrize("same_psychologist", [False, True])
async def test_time_is_rechecked_after_waiting_for_other_locks(monkeypatch, same_psychologist):
    clock = SimpleNamespace(now=datetime.now(timezone.utc))

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.now

    monkeypatch.setattr(appointments_repo, "datetime", FrozenDatetime)
    actor = make_user()
    profile = make_psychologist(actor)
    appointment = make_appointment(profile if same_psychologist else None)
    appointment.scheduled_time = clock.now + timedelta(seconds=1)
    snapshot = vars(appointment).copy()

    class DelayedSession(FakeSession):
        async def execute(self, query):
            result = await super().execute(query)
            entity = query.column_descriptions[0]["entity"]
            if entity is (Psychologist if same_psychologist else Application):
                clock.now = appointment.scheduled_time
            return result

    session = DelayedSession(appointment, profile)
    patch_session(monkeypatch, session)
    with pytest.raises(ValueError, match="время которой уже наступило"):
        await appointments_repo.reassign_appointment_to_psychologist(appointment.id, actor.id)
    assert vars(appointment) == snapshot
    assert session.rolled_back and not session.flushed


async def test_http_elapsed_appointment_returns_409_without_side_effects(monkeypatch):
    from unittest.mock import AsyncMock

    actor = make_user()
    profile = make_psychologist(actor)
    appointment = make_appointment()
    appointment.scheduled_time = datetime.now(timezone.utc) - timedelta(seconds=1)
    snapshot = vars(appointment).copy()
    session = FakeSession(appointment, profile)
    patch_session(monkeypatch, session)
    monkeypatch.setattr(appointments_service, "get_user_by_id", AsyncMock(return_value=actor))
    monkeypatch.setattr(appointments_service, "get_psychologist_by_user_id", AsyncMock(return_value=profile))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_http_app(actor)), base_url="http://test",
    ) as client:
        response = await client.post(f"/appointments/{appointment.id}/reassign")
    assert response.status_code == 409
    assert "время которой уже наступило" in response.json()["detail"]
    assert vars(appointment) == snapshot
    assert session.rolled_back and not session.flushed
