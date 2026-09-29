"""Opt-in PostgreSQL checks; each test owns an isolated, disposable schema."""
import asyncio
import importlib.util
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from psychohelp.config.config import Base
from psychohelp.models.appointments import Appointment, AppointmentStatus, AppointmentType
from psychohelp.models.psychologists import Psychologist
from psychohelp.models.users import User
from psychohelp.repositories import appointments as repository
from psychohelp.schemas.appointments import AppointmentBase
from psychohelp.services.appointments.exceptions import AppointmentNotActiveException


@pytest_asyncio.fixture(loop_scope="function")
async def database(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for isolated PostgreSQL tests")
    schema = "test_emergency_" + uuid4().hex
    admin_engine = create_async_engine(url)
    engine = create_async_engine(url, connect_args={"server_settings": {
        "search_path": schema, "application_name": schema,
    }})
    sessions = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with admin_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        @asynccontextmanager
        async def get_db():
            async with sessions() as session:
                yield session

        monkeypatch.setattr(repository, "get_async_db", get_db)
        async with sessions() as session:
            patient = User(
                id=uuid4(), first_name="Анна", last_name="Иванова", phone_number="+79991234567",
                email="patient@example.com", password="unused",
            )
            psychologist_user = User(
                id=uuid4(), first_name="Иван", last_name="Петров", phone_number="+79991234568",
                email="psychologist@example.com", password="unused",
            )
            psychologist = Psychologist(
                id=uuid4(), user=psychologist_user, experience="1", qualification="Психолог",
                consult_areas="Учёба", description="Описание", office="101",
                education="Высшее", short_description="Психолог",
            )
            appointment = Appointment(
                id=uuid4(), patient=patient, psychologist=psychologist,
                type=AppointmentType.Offline, status=AppointmentStatus.awaiting, venue="101",
                scheduled_time=datetime.now(timezone.utc) - timedelta(days=1),
                last_change_time=datetime.now(timezone.utc) - timedelta(days=2),
            )
            session.add(appointment)
            await session.commit()
        yield SimpleNamespace(
            sessions=sessions, engine=engine, admin_engine=admin_engine, schema=schema,
            appointment_id=appointment.id, patient_id=patient.id, psychologist_user_id=psychologist_user.id,
        )
    finally:
        await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin_engine.dispose()


async def test_contact_persists_and_survives_completion(database):
    db = database
    created = await repository.get_appointment_by_id(db.appointment_id, db.patient_id)
    assert created.emergency_contact is None
    for actor, value in [
        (db.patient_id, "Контакт студента"), (db.psychologist_user_id, "Контакт психолога"),
        (db.patient_id, None), (db.patient_id, "Последний контакт"),
    ]:
        changed = await repository.update_emergency_contact(db.appointment_id, actor, value)
        # Serialization after closing the session verifies eager loading of response relationships.
        assert AppointmentBase.model_validate(changed).emergency_contact == value
        read = await repository.get_appointment_by_id(db.appointment_id, actor)
        assert read.emergency_contact == value
        assert (await repository.get_appointments_by_user_id(actor))[0].emergency_contact == value
    await repository.complete_appointment_by_psychologist(db.appointment_id, db.psychologist_user_id, "Завершено")
    with pytest.raises(AppointmentNotActiveException):
        await repository.update_emergency_contact(db.appointment_id, db.patient_id, None)
    read = await repository.get_appointment_by_id(db.appointment_id, db.patient_id)
    assert read.emergency_contact == "Последний контакт"


@pytest.mark.parametrize("status", [AppointmentStatus.done, AppointmentStatus.cancelled])
async def test_contact_update_waits_for_status_transaction(database, status):
    db = database
    pending = None
    try:
        async with db.sessions() as closing_session:
            # Hold the same row lock as the UPDATE emitted by completion/cancellation.
            await closing_session.execute(
                update(Appointment).where(Appointment.id == db.appointment_id).values(status=status)
            )
            pending = asyncio.create_task(
                repository.update_emergency_contact(db.appointment_id, db.patient_id, "Too late")
            )
            async with db.admin_engine.connect() as observer:
                async with asyncio.timeout(10):
                    while True:
                        blocked = await observer.scalar(text(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE application_name = :name AND wait_event_type = 'Lock'"
                        ), {"name": db.schema})
                        await observer.commit()  # Refresh the statistics snapshot on each poll.
                        if blocked:
                            break
                        if pending.done():
                            pytest.fail("Contact update did not wait for the row lock")
                        await asyncio.sleep(0.02)
            await closing_session.commit()
        with pytest.raises(AppointmentNotActiveException):
            await asyncio.wait_for(pending, timeout=5)
        read = await repository.get_appointment_by_id(db.appointment_id, db.patient_id)
        assert read.status == status
        assert read.emergency_contact is None
    finally:
        if pending is not None:
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


async def test_migration_upgrade_and_downgrade_preserve_existing_rows(database):
    migration_path = Path(__file__).parents[1] / "alembic/versions/f3a4b5c6d7e8_add_emergency_contact_to_appointments.py"
    spec = importlib.util.spec_from_file_location("emergency_contact_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def migrate(connection, operation):
        with Operations.context(MigrationContext.configure(connection)):
            operation()

    async with database.engine.begin() as connection:
        await connection.run_sync(migrate, migration.downgrade)
        await connection.run_sync(migrate, migration.upgrade)
        assert (await connection.execute(text("SELECT emergency_contact FROM appointments"))).one() == (None,)
        column = (await connection.execute(text(
            "SELECT character_maximum_length, is_nullable FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = 'appointments' AND column_name = 'emergency_contact'"
        ), {"schema": database.schema})).one()
        assert column == (512, "YES")
        await connection.run_sync(migrate, migration.downgrade)
        assert (await connection.execute(text("SELECT id FROM appointments"))).scalar_one() == database.appointment_id
        assert await connection.scalar(text(
            "SELECT count(*) FROM information_schema.columns WHERE table_schema = :schema "
            "AND table_name = 'appointments' AND column_name = 'emergency_contact'"
        ), {"schema": database.schema}) == 0
        await connection.run_sync(migrate, migration.upgrade)
