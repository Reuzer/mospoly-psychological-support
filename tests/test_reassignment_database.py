"""PostgreSQL integration tests for appointment state changes.

The test uses only a disposable database supplied explicitly through
PSYCHOHELP_TEST_DATABASE_URL.
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from psychohelp.config.config import Base
from psychohelp.models.appointment_reschedule_requests import (
    AppointmentRescheduleRequest,
    AppointmentRescheduleStatus,
)
from psychohelp.models.appointments import Appointment, AppointmentStatus, AppointmentType
from psychohelp.models.psychologists import Psychologist
from psychohelp.models.users import User
from psychohelp.repositories import appointments as appointments_repo


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
        url,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema}},
    )
    sessions = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def get_db():
        async with sessions() as session:
            yield session

    monkeypatch.setattr(appointments_repo, "get_async_db", get_db)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with sessions() as session:
            def make_user(first_name: str) -> User:
                return User(
                    first_name=first_name,
                    last_name="Тест",
                    phone_number="+79991234567",
                    email=f"{uuid4().hex}@example.com",
                    password="test",
                )

            patient = make_user("Пациент")
            previous_user = make_user("Прежний")
            new_user = make_user("Новый")
            session.add_all([patient, previous_user, new_user])
            await session.flush()

            def make_psychologist(user: User) -> Psychologist:
                return Psychologist(
                    user_id=user.id,
                    experience="5 лет",
                    qualification="Психолог",
                    consult_areas="Стресс",
                    description="Описание",
                    office="Кабинет 1",
                    education="Высшее",
                    short_description="Психолог",
                )

            previous = make_psychologist(previous_user)
            new = make_psychologist(new_user)
            session.add_all([previous, new])
            await session.flush()

            scheduled_time = datetime.now(timezone.utc) + timedelta(days=2)
            appointment = Appointment(
                patient_id=patient.id,
                psychologist_id=previous.id,
                type=AppointmentType.Offline,
                duration=60,
                status=AppointmentStatus.awaiting,
                scheduled_time=scheduled_time,
                last_change_time=datetime.now(timezone.utc),
                venue="Кабинет 1",
            )
            session.add(appointment)
            await session.flush()

            request = AppointmentRescheduleRequest(
                appointment_id=appointment.id,
                requested_by_user_id=previous_user.id,
                status=AppointmentRescheduleStatus.pending,
                old_scheduled_time=scheduled_time,
                old_venue="Кабинет 1",
                requested_scheduled_time=scheduled_time + timedelta(days=1),
                requested_venue="Кабинет 2",
            )
            session.add(request)
            await session.commit()

            state = SimpleNamespace(
                sessions=sessions,
                appointment_id=appointment.id,
                new_user_id=new_user.id,
                new_psychologist_id=new.id,
                request_id=request.id,
            )

        yield state
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def test_reassignment_updates_appointment_and_rejects_pending_request(database):
    state = database

    result = await appointments_repo.reassign_appointment_to_psychologist(
        state.appointment_id,
        state.new_user_id,
    )

    assert result.psychologist_id == state.new_psychologist_id
    async with state.sessions() as session:
        request = await session.get(AppointmentRescheduleRequest, state.request_id)
        assert request.status == AppointmentRescheduleStatus.rejected
        assert request.responded_at is not None
        assert "переназначена" in request.rejection_comment


async def test_appointment_no_show_expires_yesterday_and_its_pending_reschedule(database):
    midnight = datetime(2026, 10, 24, tzinfo=ZoneInfo("Europe/Moscow"))
    async with database.sessions.begin() as session:
        missed = await session.get(Appointment, database.appointment_id)
        missed.scheduled_time = midnight - timedelta(seconds=1)
        today = Appointment(
            patient_id=missed.patient_id, psychologist_id=missed.psychologist_id,
            type=missed.type, status=AppointmentStatus.awaiting, scheduled_time=midnight,
            last_change_time=missed.last_change_time, venue=missed.venue,
        )
        session.add(today)
        await session.flush()
        today_id = today.id

    await appointments_repo.mark_appointment_no_shows(midnight, midnight)
    await appointments_repo.mark_appointment_no_shows(midnight, midnight + timedelta(hours=1))

    async with database.sessions() as session:
        missed = await session.get(Appointment, database.appointment_id)
        today = await session.get(Appointment, today_id)
        reschedule = await session.get(AppointmentRescheduleRequest, database.request_id)
        assert missed.status == AppointmentStatus.no_show
        assert missed.last_change_time == midnight
        assert today.status == AppointmentStatus.awaiting
        assert reschedule.status == AppointmentRescheduleStatus.rejected
        assert reschedule.responded_at == midnight
