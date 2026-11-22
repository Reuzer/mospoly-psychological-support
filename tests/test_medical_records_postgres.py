"""Проверки медкарт в PostgreSQL с отдельной временной схемой для каждого теста."""

import asyncio
import importlib.util
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
import httpx
from PIL import Image
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
from psychohelp.repositories import psy_test_attempts, psy_tests
from psychohelp.routes.controllers import medical_records, psy_test_attempts as attempt_routes
from psychohelp.routes.controllers import images, psy_tests as test_routes, users
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


async def test_profile_and_medical_records_handle_legacy_phone(database, monkeypatch):
    db = database
    monkeypatch.setattr(users_repo, "get_async_db", db.get_db)
    invalid_phone = "+70000000000"
    application = FastAPI()
    application.include_router(medical_records.router)
    application.include_router(users.router)
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://test",
        cookies={"access_token": create_access_token(db.patient.id)},
    ) as student:
        response = await student.put("/users/me", json={"phone_number": invalid_phone})
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "phone_number"]

        async with db.sessions() as session:
            patient = await session.get(User, db.patient.id)
            assert patient.phone_number == db.patient.phone_number
            patient.phone_number = invalid_phone
            await session.commit()

        response = await student.get("/users/user")
        assert response.status_code == 200
        assert response.json()["phone_number"] is None

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test",
            cookies={"access_token": create_access_token(db.staff.id)},
        ) as staff:
            response = await staff.get("/medical-records/")
            assert response.status_code == 200
            phones = {card["id"]: card["user"]["phone_number"] for card in response.json()}
            assert phones == {
                str(db.patient.id): None, str(db.another_patient.id): db.another_patient.phone_number,
            }
            response = await staff.get(f"/medical-records/{db.patient.id}")
            assert response.status_code == 200
            assert response.json()["user"]["phone_number"] is None

        response = await student.put("/users/me", json={"phone_number": "+7 (999) 123-45-68"})
        assert response.status_code == 200
        assert response.json()["phone_number"] == "+79991234568"

    async with db.sessions() as session:
        patient = await session.get(User, db.patient.id)
        assert patient.phone_number == "+79991234568"


@pytest.fixture
def assessment_api(database, monkeypatch, tmp_path):
    for repository in (users_repo, psy_tests, psy_test_attempts):
        monkeypatch.setattr(repository, "get_async_db", database.get_db)
    monkeypatch.setattr(images.config, "PSY_TEST_IMAGE_DIR", tmp_path / "psy-tests")
    app = FastAPI()
    for router in (
        test_routes.router, attempt_routes.router, attempt_routes.results_router, medical_records.router, images.router,
    ):
        app.include_router(router)

    def client(user):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, root_path="/api"),
            base_url="http://test", cookies={"access_token": create_access_token(user.id)},
        )

    return client


async def test_catalog_creates_only_tests_matching_their_type(database, assessment_api, monkeypatch):
    from psychohelp.services.rbac import permissions

    async def can_manage_catalog(_user_id, _permission):
        return True

    monkeypatch.setattr(permissions, "user_has_permission", can_manage_catalog)
    payload = {"title": "Тест", "description": "Описание"}
    async with assessment_api(database.patient) as catalog, assessment_api(database.another_patient) as admin:
        medical = payload | {"type": "Медицинский", "questions": [{"text": "Как вы себя чувствуете?"}]}
        assert (await catalog.post("/psy-tests/", json=medical)).status_code == 403
        assert (await admin.post("/psy-tests/", json=payload | {"type": "Медицинский"})).status_code == 422
        assert (await admin.post("/psy-tests/", json=medical | {"url": "https://example.org/"})).status_code == 422
        assert (await admin.post("/psy-tests/", json=medical)).status_code == 201

        external = payload | {"type": "Развлекательный"}
        assert (await catalog.post("/psy-tests/", json=external)).status_code == 422
        assert (await catalog.post("/psy-tests/", json=external | {"url": "mailto:test@example.org"})).status_code == 422
        response = await catalog.post("/psy-tests/", json=external | {"url": "https://example.org/test"})
        assert response.status_code == 201
        assert response.json()["url"] == "https://example.org/test"
        path = f"/psy-tests/{response.json()['id']}"
        assert (await catalog.post(path + "/attempts")).status_code == 404
        assert (await catalog.put(path, json={"type": "Медицинский"})).status_code == 409


async def test_medical_test_resumes_and_counts_completed_attempts(database, assessment_api):
    patient_id = database.patient.id
    record_path = f"/medical-records/{patient_id}"
    results_path = record_path + "/test-attempts"
    async with (
        assessment_api(database.staff) as psychologist,
        assessment_api(database.patient) as student,
        assessment_api(database.another_patient) as other,
    ):
        created = await psychologist.post("/psy-tests/", json={
            "title": "Самочувствие", "description": "Ретроспектива", "type": "Медицинский",
            "questions": [{"text": "Как вы спали?"}, {"text": "Как ваше настроение?"}],
        })
        assert created.status_code == 201, created.text
        path = f"/psy-tests/{created.json()['id']}"
        questions_path = path + "/questions"
        questions = (await psychologist.get(questions_path)).json()
        assert [question["position"] for question in questions] == [1, 2]
        first, second = questions
        assert first["image"] is None and second["image"] is None

        picture = BytesIO()
        Image.new("RGB", (4, 4)).save(picture, "PNG")
        image_path = f"{questions_path}/{first['id']}/image"
        uploaded = await psychologist.post(image_path, files={
            "image": ("question.png", picture.getvalue(), "image/png"),
        })
        assert uploaded.status_code == 200, uploaded.text
        first = uploaded.json()
        assert first["image"].startswith("/api/media/psy-tests/")
        assert (await student.get(first["image"])).status_code == 200

        starts = await asyncio.gather(*(student.post(path + "/attempts") for _ in range(2)))
        assert all(response.status_code == 200 for response in starts)
        attempt = starts[0].json()
        assert starts[1].json()["id"] == attempt["id"]
        assert attempt["next_question"] == first
        attempt_path = f"{path}/attempts/{attempt['id']}"
        assert (await other.get(attempt_path)).status_code == 404
        assert (await other.put(attempt_path + f"/answers/{first['id']}", json={"answer": "Чужой"})).status_code == 404
        assert (await other.get(results_path)).status_code == 403
        assert (await student.get(results_path)).status_code == 403
        assert (await psychologist.delete(image_path)).status_code == 409
        assert (await psychologist.put(questions_path, json={"questions": [{"text": "Новый вопрос"}]})).status_code == 409

        first_answer_path = f"{attempt_path}/answers/{first['id']}"
        last_answer_path = f"{attempt_path}/answers/{second['id']}"
        assert (await student.put(last_answer_path, json={"answer": "Хорошее"})).status_code == 409
        assert (await student.put(first_answer_path, json={"answer": "   "})).status_code == 422
        saved = await student.put(first_answer_path, json={"answer": "Спал хорошо"})
        assert saved.status_code == 200
        assert saved.json()["next_question"] == second
        assert (await student.post(path + "/attempts")).json() == saved.json()
        assert (await psychologist.get(record_path)).json()["tests_count"] == 0
        details_path = f"{results_path}/{attempt['id']}"
        reviewed = await psychologist.get(details_path)
        assert reviewed.status_code == 200 and reviewed.headers["cache-control"] == "no-store"
        assert reviewed.json()["answers"][0]["answer"] == "Спал хорошо"
        assert reviewed.json()["completed_at"] is None

        submitted = await asyncio.gather(*(
            student.put(last_answer_path, json={"answer": "Хорошее"}) for _ in range(2)
        ))
        assert all(response.status_code == 200 for response in submitted)
        completed = submitted[0].json()
        assert submitted[1].json() == completed
        assert completed["completed_at"] and completed["next_question"] is None
        assert [item["question"] for item in completed["answers"]] == [first, second]
        assert (await student.put(last_answer_path, json={"answer": "Другой"})).status_code == 409

        second_attempt = (await student.post(path + "/attempts")).json()
        assert second_attempt["id"] != attempt["id"]
        for question in (first, second):
            answer = await student.put(
                f"{path}/attempts/{second_attempt['id']}/answers/{question['id']}",
                json={"answer": "Повторный ответ"},
            )
            assert answer.status_code == 200
        assert (await psychologist.get(record_path)).json()["tests_count"] == 1
        assert (await psychologist.delete(path)).status_code == 200
        assert (await student.get(path)).status_code == 404
        assert (await student.post(path + "/attempts")).status_code == 404
        assert (await psychologist.get(details_path)).json() == completed
        assert len((await psychologist.get(results_path)).json()) == 2
        assert (await psychologist.get(record_path)).json()["tests_count"] == 1

    async with database.sessions() as session:
        completions = await session.scalar(select(func.count()).select_from(PsyTestCompletion))
        assert completions == 2


async def test_medical_test_restart_can_overlap_final_answer(database, assessment_api, monkeypatch):
    async with assessment_api(database.staff) as psychologist, assessment_api(database.patient) as student:
        created = await psychologist.post("/psy-tests/", json={
            "title": "Самочувствие", "description": "Описание", "type": "Медицинский",
            "questions": [{"text": "Как вы себя чувствуете?"}],
        })
        assert created.status_code == 201, created.text
        path = f"/psy-tests/{created.json()['id']}/attempts"
        started = await student.post(path)
        assert started.status_code == 200, started.text
        attempt = started.json()
        answer_path = f"{path}/{attempt['id']}/answers/{attempt['next_question']['id']}"

        attempt_locked = asyncio.Event()
        test_locked = asyncio.Event()
        get_questions = psy_test_attempts.get_questions
        require_medical_test = psy_test_attempts.require_medical_test

        async def wait_for_restart(*args):
            if not attempt_locked.is_set():
                attempt_locked.set()
                await test_locked.wait()
            return await get_questions(*args)

        async def notify_test_locked(*args, **kwargs):
            test = await require_medical_test(*args, **kwargs)
            test_locked.set()
            return test

        monkeypatch.setattr(psy_test_attempts, "get_questions", wait_for_restart)
        monkeypatch.setattr(psy_test_attempts, "require_medical_test", notify_test_locked)

        async with asyncio.timeout(10), asyncio.TaskGroup() as tasks:
            submitted = tasks.create_task(student.put(answer_path, json={"answer": "Хорошо"}))
            await attempt_locked.wait()
            restarted = tasks.create_task(student.post(path))

        completed = submitted.result()
        assert completed.status_code == 200, completed.text
        assert completed.json()["completed_at"] is not None
        next_attempt = restarted.result()
        assert next_attempt.status_code == 200, next_attempt.text
        assert next_attempt.json()["id"] != attempt["id"]
        assert next_attempt.json()["completed_at"] is None


async def test_medical_test_supports_text_and_both_choice_types(database, assessment_api):
    questions = [
        {"text": "Что вы хотите добавить?"},
        {"text": "Выберите настроение", "type": "single_choice",
         "options": [{"text": "Хорошее"}, {"text": "Спокойное"}]},
        {"text": "Что помогло вам отдохнуть?", "type": "multiple_choice",
         "options": [{"text": "Сон"}, {"text": "Прогулка"}, {"text": "Общение"}]},
    ]
    payload = {"title": "Самочувствие", "description": "Описание", "type": "Медицинский"}
    async with assessment_api(database.staff) as psychologist, assessment_api(database.patient) as student:
        for invalid in (
            {"text": "Текст", "options": [{"text": "Лишний вариант"}]},
            {"text": "Одиночный выбор", "type": "single_choice"},
            {"text": "Множественный выбор", "type": "multiple_choice", "options": [{"text": "Один"}]},
        ):
            response = await psychologist.post("/psy-tests/", json=payload | {"questions": [invalid]})
            assert response.status_code == 422

        response = await psychologist.post("/psy-tests/", json=payload | {"questions": questions})
        assert response.status_code == 201, response.text
        path = f"/psy-tests/{response.json()['id']}"
        original = (await psychologist.get(path + "/questions")).json()
        updated = await psychologist.put(path + "/questions", json={"questions": questions})
        assert updated.status_code == 200, updated.text
        text_question, single, multiple = updated.json()
        assert text_question["type"] == "text" and text_question["options"] == []
        assert [item["text"] for item in single["options"]] == ["Хорошее", "Спокойное"]
        assert [item["text"] for item in multiple["options"]] == ["Сон", "Прогулка", "Общение"]
        original_id = original[1]["options"][0]["id"]
        single_ids = [item["id"] for item in single["options"]]
        multiple_ids = [item["id"] for item in multiple["options"]]
        assert original_id not in single_ids
        assert (await psychologist.get(path + "/questions")).json() == updated.json()

        attempt = (await student.post(path + "/attempts")).json()
        answers_path = f"{path}/attempts/{attempt['id']}/answers"
        text_path = f"{answers_path}/{text_question['id']}"
        single_path = f"{answers_path}/{single['id']}"
        multiple_path = f"{answers_path}/{multiple['id']}"
        assert (await student.put(text_path, json={"option_ids": [single_ids[0]]})).status_code == 422
        text_result = await student.put(text_path, json={"answer": "Всё хорошо"})
        assert text_result.status_code == 200
        assert text_result.json()["next_question"] == single

        for body in (
            {"option_ids": single_ids},
            {"option_ids": [original_id]},
            {"option_ids": [multiple_ids[0]]},
            {"answer": "Хорошее"},
            {"answer": "Хорошее", "option_ids": [single_ids[0]]},
        ):
            assert (await student.put(single_path, json=body)).status_code == 422
        saved = await student.put(single_path, json={"option_ids": [single_ids[0]]})
        assert saved.status_code == 200
        assert saved.json()["next_question"] == multiple
        assert (await student.post(path + "/attempts")).json() == saved.json()

        for invalid_ids in ([], [multiple_ids[0], multiple_ids[0]], [single_ids[0], multiple_ids[0]]):
            assert (await student.put(multiple_path, json={"option_ids": invalid_ids})).status_code == 422
        record_path = f"/medical-records/{database.patient.id}"
        assert (await psychologist.get(record_path)).json()["tests_count"] == 0
        completed = await student.put(multiple_path, json={"option_ids": multiple_ids[:2][::-1]})
        assert completed.status_code == 200, completed.text
        result = completed.json()
        assert result["completed_at"] and result["next_question"] is None
        assert (await student.put(multiple_path, json={"option_ids": multiple_ids[:2]})).json() == result
        assert (await student.put(multiple_path, json={"option_ids": multiple_ids[1:]})).status_code == 409
        assert result["answers"][0]["answer"] == "Всё хорошо"
        assert result["answers"][1]["option_ids"] == [single_ids[0]]
        assert result["answers"][2]["option_ids"] == multiple_ids[:2]
        assert result["answers"][2]["question"] == multiple
        reviewed = await psychologist.get(f"{record_path}/test-attempts/{attempt['id']}")
        assert reviewed.json() == result
        assert (await psychologist.get(record_path)).json()["tests_count"] == 1


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
