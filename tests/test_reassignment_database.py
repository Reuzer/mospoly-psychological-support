"""PostgreSQL integration tests. Use an explicitly supplied disposable database URL."""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from psychohelp.config.config import Base
from psychohelp.constants.rbac import RoleCode
from psychohelp.models.applications import Application, ApplicationStatus
from psychohelp.models.appointments import Appointment, AppointmentStatus
from psychohelp.models.appointment_reschedule_requests import AppointmentRescheduleStatus
from psychohelp.models.psychologists import Psychologist
from psychohelp.models.roles import Role
from psychohelp.models.users import User
from psychohelp.repositories import applications as applications_repo
from psychohelp.repositories import appointments as appointments_repo
from psychohelp.repositories import appointment_reschedule_requests as reschedules_repo
from psychohelp.schemas.applications import ApplicationReassignRequest
from psychohelp.services.applications import applications as applications_service
from psychohelp.services.applications.exceptions import AccessDeniedError, ConflictError
from psychohelp.services.appointments import appointments as appointments_service


@pytest.fixture
async def database(monkeypatch):
    url = os.getenv("PSYCHOHELP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set PSYCHOHELP_TEST_DATABASE_URL to run PostgreSQL integration tests")
    schema = "test_reassignment_" + uuid4().hex
    admin = create_async_engine(url, poolclass=NullPool)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url, poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema}},
    )
    sessions = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def get_db():
        async with sessions() as session:
            yield session

    for module in (applications_repo, appointments_repo, reschedules_repo):
        monkeypatch.setattr(module, "get_async_db", get_db)
    import psychohelp.config.config as config_module
    monkeypatch.setattr(config_module, "async_session", sessions)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            role = Role(code=RoleCode.PSYCHOLOGIST, name="Психолог")

            def user(name, roles):
                return User(
                    first_name=name, last_name="Тест", phone_number="+79991234567",
                    email=f"{uuid4().hex}@example.com", password="test", roles=roles,
                )

            patient = user("Пациент", [])
            previous = user("Прежний", [role])
            actor = user("Новый", [role])
            session.add_all([patient, previous, actor])
            await session.flush()

            def psychologist(user):
                return Psychologist(
                    user_id=user.id, experience="5 лет", qualification="Психолог",
                    consult_areas="Стресс", description="Описание", office="Кабинет 1",
                    education="Высшее", short_description="Психолог",
                )

            old_profile, profile = psychologist(previous), psychologist(actor)
            session.add_all([old_profile, profile])
            await session.flush()
            application = Application(
                user_id=patient.id, university_status="студент",
                problem_description="Тестовая консультация",
                status=ApplicationStatus.AWAITING_USER_CONFIRMATION.value,
                psychologist_id=old_profile.id, assigned_to=previous.id,
                meeting_type="offline", location_address="Кабинет 1",
                scheduled_at=datetime.now(timezone.utc) + timedelta(days=2),
                confirmation_requested_at=datetime.now(timezone.utc), version=3,
            )
            session.add(application)
            await session.commit()
            state = SimpleNamespace(
                sessions=sessions, patient=patient, previous=previous, actor=actor,
                profile=profile, application=application,
            )
        yield state
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def confirm(state, version=3, actor_id=None):
    return await applications_service.confirm_application(
        state.application.id, version, actor_id or state.patient.id, True,
    )


async def appointment_count(state):
    async with state.sessions() as session:
        return await session.scalar(select(func.count()).select_from(Appointment))


async def test_reassigned_offer_requires_new_version_and_creates_exactly_one_appointment(database):
    state = database
    changed = await applications_service.reassign_application(
        state.application.id,
        ApplicationReassignRequest(meeting_type="online", meeting_url="https://example.com/new"),
        state.actor.id,
    )
    with pytest.raises(ConflictError):
        await confirm(state)
    assert await appointment_count(state) == 0
    completed = await confirm(state, changed.version)
    assert completed.status == "completed"
    assert completed.appointment.psychologist_id == state.profile.id
    assert completed.appointment.venue == "https://example.com/new"
    assert completed.appointment.patient_id == state.patient.id
    with pytest.raises(ConflictError):
        await confirm(state, changed.version)
    assert await appointment_count(state) == 1


async def test_only_patient_can_confirm_even_if_service_is_called_with_is_owner_true(database):
    with pytest.raises(AccessDeniedError):
        await confirm(database, actor_id=database.actor.id)
    assert await appointment_count(database) == 0


async def test_parallel_confirmations_create_one_appointment(database):
    results = await asyncio.wait_for(
        asyncio.gather(confirm(database), confirm(database), return_exceptions=True), 10,
    )
    assert sum(isinstance(result, Application) for result in results) == 1
    assert sum(isinstance(result, ConflictError) for result in results) == 1
    assert await appointment_count(database) == 1


async def test_reassignment_racing_confirmation_cannot_confirm_changed_terms(database):
    state = database
    results = await asyncio.wait_for(asyncio.gather(
        applications_service.reassign_application(
            state.application.id, ApplicationReassignRequest(), state.actor.id,
        ),
        confirm(state),
        return_exceptions=True,
    ), 10)
    current = await applications_repo.get_application_by_id(state.application.id)
    if current.status == "completed":
        assert current.appointment.psychologist_id == state.application.psychologist_id
        assert isinstance(results[0], Exception)
        assert await appointment_count(state) == 1
    else:
        assert current.psychologist_id == state.profile.id
        assert isinstance(results[1], ConflictError)
        assert await appointment_count(state) == 0


async def test_appointment_reassignment_invalidates_old_transfer_and_old_psychologist_access(database):
    state = database
    completed = await confirm(state)
    appointment_id = completed.appointment_id
    request = await reschedules_repo.create_reschedule_request(
        appointment_id=appointment_id, psychologist_user_id=state.previous.id,
        scheduled_time=state.application.scheduled_at + timedelta(days=1),
        remind_time=None, venue="Кабинет 2", comment=None,
    )
    await appointments_repo.update_emergency_contact(appointment_id, state.patient.id, "Мама, +79991234567")
    result = await appointments_service.reassign_appointment_to_self(appointment_id, state.actor.id)
    assert result.emergency_contact == "Мама, +79991234567"
    assert result.psychologist_id == state.profile.id
    assert result.status == AppointmentStatus.awaiting
    with pytest.raises(ValueError, match="уже обработан"):
        await reschedules_repo.confirm_reschedule_request(request.id, state.patient.id)
    with pytest.raises(PermissionError):
        await appointments_repo.complete_appointment_by_psychologist(appointment_id, state.previous.id, "Комментарий")
    current = await applications_repo.get_application_by_id(state.application.id)
    assert current.psychologist_id == state.profile.id
    assert current.assigned_to == state.actor.id
    requests = await reschedules_repo.get_reschedule_requests_by_appointment(appointment_id, state.patient.id)
    assert requests[0].status == AppointmentRescheduleStatus.rejected
    assert result.scheduled_time == state.application.scheduled_at


@pytest.mark.parametrize("same_psychologist", [False, True])
async def test_elapsed_appointment_reassignment_rolls_back_all_related_data(database, same_psychologist):
    state = database
    completed = await confirm(state)
    appointment_id = completed.appointment_id
    request = await reschedules_repo.create_reschedule_request(
        appointment_id=appointment_id, psychologist_user_id=state.previous.id,
        scheduled_time=state.application.scheduled_at + timedelta(days=1),
        remind_time=None, venue="Кабинет 2", comment=None,
    )
    from sqlalchemy import update
    past_time = datetime.now(timezone.utc) - timedelta(seconds=1)
    async with state.sessions() as session:
        await session.execute(update(Appointment).where(Appointment.id == appointment_id).values(scheduled_time=past_time))
        await session.commit()
    before = await applications_repo.get_application_by_id(state.application.id)
    actor_id = state.previous.id if same_psychologist else state.actor.id
    with pytest.raises(ValueError, match="время которой уже наступило"):
        await appointments_service.reassign_appointment_to_self(appointment_id, actor_id)
    current = await applications_repo.get_application_by_id(state.application.id)
    assert current.version == before.version
    assert current.updated_at == before.updated_at
    assert current.psychologist_id == before.psychologist_id
    assert current.assigned_to == before.assigned_to
    assert current.appointment.psychologist_id == before.appointment.psychologist_id
    assert current.appointment.scheduled_time == past_time
    assert current.appointment.last_change_time == before.appointment.last_change_time
    requests = await reschedules_repo.get_reschedule_requests_by_appointment(appointment_id, state.patient.id)
    assert requests[0].id == request.id
    assert requests[0].status == AppointmentRescheduleStatus.pending
    assert requests[0].responded_at is None


async def test_transfer_cannot_move_appointment_to_elapsed_time(database):
    state = database
    completed = await confirm(state)
    request = await reschedules_repo.create_reschedule_request(
        appointment_id=completed.appointment_id, psychologist_user_id=state.previous.id,
        scheduled_time=state.application.scheduled_at + timedelta(days=1),
        remind_time=None, venue="Кабинет 2", comment=None,
    )
    from sqlalchemy import update
    from psychohelp.models.appointment_reschedule_requests import AppointmentRescheduleRequest
    async with state.sessions() as session:
        await session.execute(
            update(AppointmentRescheduleRequest).where(AppointmentRescheduleRequest.id == request.id)
            .values(requested_scheduled_time=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
        await session.commit()
    with pytest.raises(ValueError, match="время, которое уже наступило"):
        await reschedules_repo.confirm_reschedule_request(request.id, state.patient.id)
    async with state.sessions() as session:
        appointment = await session.get(Appointment, completed.appointment_id)
        current_request = await session.get(AppointmentRescheduleRequest, request.id)
        assert appointment.scheduled_time == state.application.scheduled_at
        assert appointment.venue == "Кабинет 1"
        assert current_request.status == AppointmentRescheduleStatus.pending
        assert current_request.responded_at is None


async def test_confirmation_rechecks_time_after_locking_psychologist(database, monkeypatch):
    from sqlalchemy import event
    from psychohelp.services.applications.exceptions import ValidationError

    state = database
    clock = SimpleNamespace(now=datetime.now(timezone.utc))

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.now

    monkeypatch.setattr(applications_repo, "datetime", FrozenDatetime)
    engine = state.sessions.kw["bind"].sync_engine

    def advance_time_after_initial_validation(connection, cursor, statement, parameters, context, executemany):
        if "FROM psychologists" in statement and "FOR UPDATE" in statement:
            clock.now = state.application.scheduled_at

    event.listen(engine, "before_cursor_execute", advance_time_after_initial_validation)
    try:
        with pytest.raises(ValidationError, match="не могут быть в прошлом"):
            await confirm(state)
    finally:
        event.remove(engine, "before_cursor_execute", advance_time_after_initial_validation)
    current = await applications_repo.get_application_by_id(state.application.id)
    assert current.status == ApplicationStatus.AWAITING_USER_CONFIRMATION
    assert current.version == state.application.version
    assert current.appointment_id is None
    assert await appointment_count(state) == 0


@pytest.mark.parametrize("unavailable", [None, "sick", "vacation"])
async def test_transfer_rechecks_current_psychologist_availability(database, unavailable):
    from psychohelp.models.psychologist_statuses import PsychologistStatus, PsychologistStatusType
    state = database
    completed = await confirm(state)
    new_time = state.application.scheduled_at + timedelta(days=1)
    request = await reschedules_repo.create_reschedule_request(
        appointment_id=completed.appointment_id, psychologist_user_id=state.previous.id,
        scheduled_time=new_time, remind_time=None, venue="Кабинет 2", comment=None,
    )
    if unavailable:
        async with state.sessions() as session:
            session.add(PsychologistStatus(
                pid=state.previous.id, status=PsychologistStatusType(unavailable),
                start_date=new_time - timedelta(hours=1), end_date=new_time + timedelta(hours=1),
            ))
            await session.commit()
        with pytest.raises(ValueError, match="недоступен"):
            await reschedules_repo.confirm_reschedule_request(request.id, state.patient.id)
    else:
        result = await reschedules_repo.confirm_reschedule_request(request.id, state.patient.id)
        assert result.status == AppointmentRescheduleStatus.confirmed
    async with state.sessions() as session:
        appointment = await session.get(Appointment, completed.appointment_id)
        assert appointment.scheduled_time == (state.application.scheduled_at if unavailable else new_time)
        assert appointment.venue == ("Кабинет 1" if unavailable else "Кабинет 2")
    requests = await reschedules_repo.get_reschedule_requests_by_appointment(completed.appointment_id, state.patient.id)
    assert requests[0].status == (AppointmentRescheduleStatus.pending if unavailable else AppointmentRescheduleStatus.confirmed)


async def test_partial_article_update_preserves_slug_and_metadata(database, monkeypatch):
    from unittest.mock import AsyncMock
    from psychohelp.models.articles import Article
    from psychohelp.routes.controllers import articles as articles_controller
    from psychohelp.schemas.articles import ArticleUpdateRequest
    import psychohelp.services.rbac.permissions as permissions

    state = database
    published_at = datetime.now(timezone.utc)
    async with state.sessions() as session:
        article = Article(
            slug="original-slug", title="Старый заголовок", text="Старый текст",
            image="/image/cover.jpg", date=published_at, author="Автор",
            description="Сохранённое описание",
        )
        session.add(article)
        await session.commit()
        article_id = article.id
    monkeypatch.setattr(permissions, "user_has_permission", AsyncMock(return_value=True))
    await articles_controller.update_article(
        article_id, ArticleUpdateRequest(title="Новый заголовок", text="Новый текст"),
        current_user=SimpleNamespace(id=state.actor.id),
    )
    async with state.sessions() as session:
        current = await session.get(Article, article_id)
        assert current.title == "Новый заголовок"
        assert current.text == "Новый текст"
        assert current.slug == "original-slug"
        assert current.image == "/image/cover.jpg"
        assert current.date == published_at
        assert current.author == "Автор"
        assert current.description == "Сохранённое описание"
