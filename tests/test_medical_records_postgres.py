"""Проверки медкарт в PostgreSQL с отдельной временной схемой для каждого теста."""

import asyncio
import importlib.util
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from psychohelp.config.config import Base
from psychohelp.constants.rbac import RoleCode
from psychohelp.dependencies.auth import get_current_user
from psychohelp.models.appointments import Appointment, AppointmentStatus, AppointmentType
from psychohelp.models.assessment_completions import PsyTestCompletion, SurveyCompletion
from psychohelp.models.psy_tests import PsyTest, TestType as PsyTestType
from psychohelp.models.psychologists import Psychologist
from psychohelp.models.roles import Role
from psychohelp.models.users import User
from psychohelp.repositories import create_access_token
from psychohelp.repositories import medical_records as repo, users as users_repo
from psychohelp.routes.controllers import medical_records, users
from psychohelp.schemas.medical_records import MedicalRecordResponse
from psychohelp.schemas.users import UserResponse
from psychohelp.services import medical_records as service
from psychohelp.services.medical_record_exceptions import (
    MedicalRecordNotFoundException,
    MedicalRecordNoteVersionConflict,
)


@pytest_asyncio.fixture(loop_scope="function")
async def database(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Для проверок PostgreSQL требуется TEST_DATABASE_URL")
    schema = "test_medical_records_" + uuid4().hex
    admin = create_async_engine(url)
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    sessions = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        @asynccontextmanager
        async def get_db():
            async with sessions() as session:
                yield session

        monkeypatch.setattr(repo, "get_async_db", get_db)
        async with sessions() as session:
            user_role = Role(code=RoleCode.USER, name="Обучающийся")
            psychologist_role = Role(code=RoleCode.PSYCHOLOGIST, name="Психолог")
            admin_role = Role(code=RoleCode.ADMIN, name="Администратор")

            def user(name, roles):
                return User(
                    id=uuid4(), first_name=name, last_name="Тест", phone_number="+79991234567",
                    email=f"{uuid4().hex}@example.com", password="secret",
                    roles=roles, study_group="241-111",
                )

            patient = user("Пациент", [user_role])
            another_patient = user("Другой", [user_role, admin_role])
            staff = user("Психолог", [psychologist_role])
            another_staff = user("Второй", [psychologist_role])

            def psychologist(staff_user):
                return Psychologist(
                    id=uuid4(), user=staff_user, experience="5", qualification="Психолог",
                    consult_areas="Учёба", description="Описание", office="101",
                    education="Высшее", short_description="Психолог",
                )

            psychologist_one = psychologist(staff)
            psychologist_two = psychologist(another_staff)
            session.add_all([patient, another_patient, psychologist_one, psychologist_two])
            await session.commit()
        yield SimpleNamespace(
            sessions=sessions, engine=engine, schema=schema, get_db=get_db, patient=patient,
            another_patient=another_patient, staff=staff,
            psychologist_one=psychologist_one, psychologist_two=psychologist_two,
        )
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def test_one_card_per_user_including_users_without_appointments(database):
    db = database
    cards = await service.get_medical_record_list()
    assert {card.id for card in cards} == {db.patient.id, db.another_patient.id}
    assert len(cards) == 2
    assert all(card.note is None for card in cards)
    for user in (db.patient, db.another_patient):
        record = await service.get_medical_record_by_user_id(user.id)
        assert record.id == record.user.id == user.id
        assert record.note is None and record.note_version == 0
        assert record.next_appointment is None
        assert record.completed_appointments == []
        assert record.tests_count == record.surveys_count == 0


async def test_missing_or_non_patient_user_has_no_record(database):
    for user_id in (uuid4(), database.staff.id):
        assert await repo.get_medical_record_by_user_id(user_id) is None
        with pytest.raises(MedicalRecordNotFoundException):
            await repo.update_medical_record_note(user_id, "Заметка", 0)


async def test_appointments_use_time_id_and_include_all_completed(database, monkeypatch):
    db = database
    now = datetime(2035, 1, 1, tzinfo=timezone.utc)

    class FixedDatetime:
        @staticmethod
        def now(_timezone):
            return now

    monkeypatch.setattr(repo, "datetime", FixedDatetime)

    def appointment(status, scheduled_time, *, appointment_id=None, psychologist=None, patient=None):
        return Appointment(
            id=appointment_id or uuid4(), patient_id=(patient or db.patient).id,
            psychologist_id=(psychologist or db.psychologist_one).id,
            type=AppointmentType.Offline, duration=60, status=status, scheduled_time=scheduled_time,
            last_change_time=now, venue="101", psychologist_comment="Внутренний комментарий",
            conclusion="Комментарий пациенту", emergency_contact="Контакт",
        )

    first = appointment(AppointmentStatus.awaiting, now + timedelta(days=1),
                        appointment_id=UUID(int=1))
    second = appointment(AppointmentStatus.awaiting, now + timedelta(days=1),
                         appointment_id=UUID(int=2), psychologist=db.psychologist_two)
    completed = [appointment(AppointmentStatus.done, now - timedelta(days=i)) for i in range(105)]
    completed.append(appointment(AppointmentStatus.done, now + timedelta(days=10)))
    async with db.sessions() as session:
        session.add_all([
            second, first, *completed,
            appointment(AppointmentStatus.awaiting, now - timedelta(seconds=1)),
            appointment(AppointmentStatus.awaiting, now),
            appointment(AppointmentStatus.awaiting, now + timedelta(days=2)),
            appointment(AppointmentStatus.cancelled, now + timedelta(minutes=1)),
            appointment(AppointmentStatus.done, now, patient=db.another_patient),
            appointment(AppointmentStatus.awaiting, now + timedelta(minutes=1), patient=db.another_patient),
        ])
        await session.commit()

    record = await service.get_medical_record_by_user_id(db.patient.id)
    assert record.next_appointment.id == first.id
    assert {item.id for item in record.completed_appointments} == {item.id for item in completed}
    assert record.next_appointment.psychologist.user.id == db.staff.id
    assert record.next_appointment.psychologist_comment == "Внутренний комментарий"
    assert record.completed_appointments[0].patient_comment == "Комментарий пациенту"
    assert "note" not in record.completed_appointments[0].patient.model_dump()
    async with db.sessions() as session:
        await session.execute(
            update(Appointment).where(
                Appointment.patient_id == db.patient.id,
                Appointment.status == AppointmentStatus.awaiting,
                Appointment.scheduled_time > now,
            ).values(status=AppointmentStatus.cancelled)
        )
        await session.commit()
    record = await service.get_medical_record_by_user_id(db.patient.id)
    assert record.next_appointment is None
    assert len(record.completed_appointments) == len(completed)


async def test_counts_distinct_completed_medical_tests_and_surveys(database):
    db = database
    medical = [PsyTest(id=uuid4(), title="Тест", description="Описание", type=PsyTestType.MEDICAL)
               for _ in range(3)]
    entertaining = PsyTest(id=uuid4(), title="Тест", description="Описание", type=PsyTestType.ENTERTAINING)
    surveys = [uuid4(), uuid4(), uuid4()]
    async with db.sessions() as session:
        session.add_all([*medical, entertaining])
        await session.flush()
        session.add_all([
            PsyTestCompletion(user_id=db.patient.id, test_id=item.id)
            for item in [medical[0], medical[0], medical[1], entertaining]
        ] + [
            PsyTestCompletion(user_id=db.another_patient.id, test_id=medical[2].id),
            *[SurveyCompletion(user_id=db.patient.id, survey_id=survey_id)
              for survey_id in [surveys[0], surveys[0], surveys[1]]],
            SurveyCompletion(user_id=db.another_patient.id, survey_id=surveys[2]),
        ])
        await session.commit()
    record = await service.get_medical_record_by_user_id(db.patient.id)
    assert record.tests_count == 2
    assert record.surveys_count == 2
    other_record = await service.get_medical_record_by_user_id(db.another_patient.id)
    assert other_record.tests_count == other_record.surveys_count == 1


async def test_concurrent_note_updates_cannot_overwrite_each_other(database):
    db = database
    results = await asyncio.gather(
        repo.update_medical_record_note(db.patient.id, "Правка первого психолога", 0),
        repo.update_medical_record_note(db.patient.id, "Правка второго психолога", 0),
        return_exceptions=True,
    )
    assert sum(isinstance(result, User) for result in results) == 1
    assert sum(isinstance(result, MedicalRecordNoteVersionConflict) for result in results) == 1
    record = await service.get_medical_record_by_user_id(db.patient.id)
    winner = next(result for result in results if isinstance(result, User))
    assert record.note == winner.note
    assert record.note_version == 1
    assert next(card for card in await service.get_medical_record_list()
                if card.id == db.patient.id).note == winner.note
    await repo.update_medical_record_note(db.patient.id, None, 1)
    with pytest.raises(MedicalRecordNoteVersionConflict):
        await repo.update_medical_record_note(db.patient.id, "Устаревшая правка", 1)
    record = await service.get_medical_record_by_user_id(db.patient.id)
    assert record.note is None and record.note_version == 2


async def test_note_lifecycle_through_http(database):
    db = database
    application = FastAPI()
    application.include_router(medical_records.router)
    application.dependency_overrides[get_current_user] = lambda: db.staff
    path = f"/medical-records/{db.patient.id}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test",
    ) as client:
        assert (await client.get(path)).json()["note_version"] == 0
        response = await client.patch(path + "/note", json={"note": "Заметка", "note_version": 0})
        assert response.status_code == 200
        assert response.json() == {"note": "Заметка", "note_version": 1}
        assert (await client.patch(path + "/note", json={"note": "Другая", "note_version": 0})).status_code == 409
        record = (await client.get(path)).json()
        assert record["note"] == "Заметка" and "note" not in record["user"]
        application.dependency_overrides[get_current_user] = lambda: db.patient
        assert (await client.get(path)).status_code == 403
        assert (await client.patch(path + "/note", json={"note": None, "note_version": 1})).status_code == 403


async def test_get_endpoints_and_student_profile_through_cookie_auth(database, monkeypatch):
    db = database
    monkeypatch.setattr(users_repo, "get_async_db", db.get_db)
    now = datetime.now(timezone.utc)
    next_id, done_id = uuid4(), uuid4()
    survey_id = uuid4()
    async with db.sessions() as session:
        psy_test = PsyTest(
            id=uuid4(), title="Медицинский тест", description="Описание", type=PsyTestType.MEDICAL,
        )
        session.add(psy_test)
        await session.flush()
        session.add_all([
            Appointment(
                id=appointment_id, patient_id=db.patient.id, psychologist_id=db.psychologist_one.id,
                type=AppointmentType.Offline, duration=60, status=status,
                scheduled_time=scheduled_time, last_change_time=now, venue="101",
                psychologist_comment="Комментарий специалистам", conclusion="Комментарий пациенту",
            )
            for appointment_id, status, scheduled_time in [
                (next_id, AppointmentStatus.awaiting, now + timedelta(days=1)),
                (done_id, AppointmentStatus.done, now - timedelta(days=1)),
                (uuid4(), AppointmentStatus.cancelled, now + timedelta(hours=1)),
                (uuid4(), AppointmentStatus.awaiting, now - timedelta(hours=1)),
            ]
        ] + [
            PsyTestCompletion(user_id=db.patient.id, test_id=psy_test.id),
            PsyTestCompletion(user_id=db.patient.id, test_id=psy_test.id),
            SurveyCompletion(user_id=db.patient.id, survey_id=survey_id),
            SurveyCompletion(user_id=db.patient.id, survey_id=survey_id),
        ])
        await session.commit()
    await repo.update_medical_record_note(db.patient.id, "Общая заметка специалистов", 0)
    application = FastAPI()
    application.include_router(medical_records.router)
    application.include_router(users.router)
    path = f"/medical-records/{db.patient.id}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test",
        cookies={"access_token": create_access_token(db.staff.id)},
    ) as client:
        # Проверяем весь путь: cookie, поиск пользователя в БД, репозиторий и сериализацию.
        response = await client.get("/medical-records/")
        assert response.status_code == 200
        previews = response.json()
        assert len(previews) == 2
        preview = next(item for item in previews if item["id"] == str(db.patient.id))
        assert set(preview) == {"id", "user", "note"}
        assert preview["note"] == "Общая заметка специалистов"
        assert preview["user"] == UserResponse.model_validate(db.patient).model_dump(mode="json")

        response = await client.get(path)
        assert response.status_code == 200
        record = response.json()
        assert set(record) == {
            "id", "user", "note", "note_version", "next_appointment",
            "completed_appointments", "tests_count", "surveys_count",
        }
        assert record["id"] == preview["id"]
        assert record["user"] == preview["user"]
        assert record["note"] == preview["note"] and record["note_version"] == 1
        assert record["next_appointment"]["id"] == str(next_id)
        assert [item["id"] for item in record["completed_appointments"]] == [str(done_id)]
        assert record["completed_appointments"][0]["psychologist_comment"] == "Комментарий специалистам"
        assert record["tests_count"] == record["surveys_count"] == 1

        client.cookies.clear()
        client.cookies.set("access_token", create_access_token(db.patient.id))
        assert (await client.get("/medical-records/")).status_code == 403
        assert (await client.get(path)).status_code == 403
        response = await client.get("/users/user")
        assert response.status_code == 200
        profile = response.json()
        assert "note" not in profile and "note_version" not in profile
        assert "Общая заметка специалистов" not in response.text
        assert "password" not in profile


async def test_migration_preserves_users_and_initializes_notes(database):
    path = Path(__file__).parents[1] / "alembic/versions/a6b7c8d9e0f1_add_medical_records.py"
    spec = importlib.util.spec_from_file_location("medical_records_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def migrate(connection, operation):
        with Operations.context(MigrationContext.configure(connection)):
            operation()

    async with database.engine.begin() as connection:
        await connection.run_sync(migrate, migration.downgrade)
        await connection.run_sync(migrate, migration.upgrade)
        rows = (await connection.execute(text("SELECT note, note_version FROM users"))).all()
        assert len(rows) == 4
        assert all(row == (None, 0) for row in rows)
        await connection.run_sync(migrate, migration.downgrade)
        assert await connection.scalar(text("SELECT count(*) FROM users")) == 4
        await connection.run_sync(migrate, migration.upgrade)
    async with database.sessions() as session:
        with pytest.raises(IntegrityError):
            await session.execute(text("UPDATE users SET note_version = -1"))
        await session.rollback()
    # Сериализация после закрытия сессии также проверяет загрузку всех связей.
    record = await repo.get_medical_record_by_user_id(database.patient.id)
    assert MedicalRecordResponse.model_validate(record).note_version == 0


async def test_completions_are_removed_with_patient(database):
    db = database
    async with db.sessions() as session:
        psy_test = PsyTest(id=uuid4(), title="Тест", description="Описание", type=PsyTestType.MEDICAL)
        session.add(psy_test)
        await session.flush()
        session.add_all([
            PsyTestCompletion(user_id=db.patient.id, test_id=psy_test.id),
            SurveyCompletion(user_id=db.patient.id, survey_id=uuid4()),
        ])
        await session.commit()
        await session.execute(delete(User).where(User.id == db.patient.id))
        await session.commit()
        assert await session.scalar(select(func.count()).select_from(PsyTestCompletion)) == 0
        assert await session.scalar(select(func.count()).select_from(SurveyCompletion)) == 0
    assert await repo.get_medical_record_by_user_id(db.patient.id) is None
