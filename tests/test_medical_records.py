from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
import httpx
import pytest

from psychohelp.constants.rbac import RoleCode
from psychohelp.dependencies.auth import get_current_user
from psychohelp.repositories import medical_records as repo
from psychohelp.routes.controllers import medical_records, users
from psychohelp.schemas.appointments import AppointmentBase, UserFullResponse
from psychohelp.schemas.users import UserResponse, UserUpdateRequest
from psychohelp.services.medical_record_exceptions import (
    MedicalRecordNotFoundException,
    MedicalRecordNoteVersionConflict,
)


def make_user(*roles):
    return SimpleNamespace(
        id=uuid4(), first_name="Анна", middle_name=None, last_name="Иванова",
        phone_number="+79991234567", email=f"{uuid4().hex}@example.com",
        social_media="https://example.com", study_group="241-111", password="secret",
        note="Общая заметка", note_version=2,
        roles=[SimpleNamespace(code=role, name=role.value, description=None) for role in roles],
    )


@pytest.fixture
def patient():
    return make_user(RoleCode.USER)


@pytest.fixture
def application():
    application = FastAPI()
    application.include_router(medical_records.router)
    application.include_router(users.router)
    return application


async def send(application, role, method, path, **kwargs):
    if role is not None:
        actor = make_user(*role) if isinstance(role, tuple) else make_user(role)
        application.dependency_overrides[get_current_user] = lambda: actor
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test",
    ) as client:
        return await client.request(method, path, **kwargs)


@pytest.mark.parametrize("role, status", [
    (None, 401), (RoleCode.USER, 403), (RoleCode.CONTENT_MANAGER, 403),
    (RoleCode.PSYCHOLOGIST, 200), (RoleCode.ADMIN, 200),
    ((RoleCode.USER, RoleCode.PSYCHOLOGIST), 200),
])
@pytest.mark.parametrize("method, path", [
    ("GET", "/medical-records/"),
    ("GET", "/medical-records/{user_id}"),
    ("PATCH", "/medical-records/{user_id}/note"),
])
async def test_access_to_medical_records(application, patient, monkeypatch, role, status, method, path):
    list_mock = AsyncMock(return_value=[patient])
    detail_mock = AsyncMock(return_value={
        "id": patient.id, "user": patient, "note": patient.note,
        "note_version": patient.note_version, "next_appointment": None,
        "completed_appointments": [], "tests_count": 0, "surveys_count": 0,
    })
    update_mock = AsyncMock(return_value=patient)
    monkeypatch.setattr(repo, "get_medical_record_list", list_mock)
    monkeypatch.setattr(repo, "get_medical_record_by_user_id", detail_mock)
    monkeypatch.setattr(repo, "update_medical_record_note", update_mock)
    response = await send(application, role, method, path.format(user_id=patient.id),
                          **({"json": {"note": "Правка", "note_version": 2}} if method == "PATCH" else {}))
    assert response.status_code == status
    if status != 200:
        list_mock.assert_not_awaited()
        detail_mock.assert_not_awaited()
        update_mock.assert_not_awaited()
    else:
        body = response.json()
        if path.endswith("/"):
            body = body[0]
            assert set(body) == {"id", "user", "note"}
        if "user" in body:
            assert body["id"] == str(patient.id)
            assert body["user"] == UserResponse.model_validate(patient).model_dump(mode="json")
            assert "note" not in body["user"]
            assert "password" not in body["user"]


@pytest.mark.parametrize("method, suffix", [("GET", ""), ("PATCH", "/note")])
async def test_missing_record_returns_404(application, monkeypatch, method, suffix):
    monkeypatch.setattr(repo, "get_medical_record_by_user_id", AsyncMock(return_value=None))
    monkeypatch.setattr(repo, "update_medical_record_note",
                        AsyncMock(side_effect=MedicalRecordNotFoundException(uuid4())))
    response = await send(application, RoleCode.PSYCHOLOGIST, method,
                          f"/medical-records/{uuid4()}{suffix}",
                          **({"json": {"note": None, "note_version": 0}} if suffix else {}))
    assert response.status_code == 404


async def test_empty_preview_list(application, monkeypatch):
    monkeypatch.setattr(repo, "get_medical_record_list", AsyncMock(return_value=[]))
    response = await send(application, RoleCode.PSYCHOLOGIST, "GET", "/medical-records/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("method, suffix", [("GET", ""), ("PATCH", "/note")])
async def test_invalid_user_uuid(application, method, suffix):
    response = await send(application, RoleCode.PSYCHOLOGIST, method,
                          f"/medical-records/not-a-uuid{suffix}",
                          **({"json": {"note": None, "note_version": 0}} if suffix else {}))
    assert response.status_code == 422


async def test_note_conflict_returns_409(application, monkeypatch):
    monkeypatch.setattr(repo, "update_medical_record_note",
                        AsyncMock(side_effect=MedicalRecordNoteVersionConflict()))
    response = await send(application, RoleCode.PSYCHOLOGIST, "PATCH",
                          f"/medical-records/{uuid4()}/note", json={"note": "Правка", "note_version": 0})
    assert response.status_code == 409


@pytest.mark.parametrize("payload", [
    {}, {"note": "Правка"}, {"note_version": 0}, {"note": 42, "note_version": 0},
    {"note": [], "note_version": 0}, {"note": None, "note_version": -1},
    {"note": None, "note_version": True}, {"note": None, "note_version": 0.5},
    {"note": None, "note_version": "0"}, {"note": None, "note_version": None},
    {"note": None, "note_version": 0, "user_id": str(uuid4())},
])
async def test_note_validation(application, monkeypatch, payload):
    update = AsyncMock()
    monkeypatch.setattr(repo, "update_medical_record_note", update)
    response = await send(application, RoleCode.PSYCHOLOGIST, "PATCH",
                          f"/medical-records/{uuid4()}/note", json=payload)
    assert response.status_code == 422
    update.assert_not_awaited()


@pytest.mark.parametrize("note", [None, "", "Текст\nзаметки"])
async def test_note_accepts_null_and_preserves_text(application, patient, monkeypatch, note):
    patient.note = note
    patient.note_version = 3
    update = AsyncMock(return_value=patient)
    monkeypatch.setattr(repo, "update_medical_record_note", update)
    response = await send(application, RoleCode.ADMIN, "PATCH", f"/medical-records/{patient.id}/note",
                          json={"note": note, "note_version": 2})
    assert response.status_code == 200
    assert response.json() == {"note": note, "note_version": 3}
    update.assert_awaited_once_with(patient.id, note, 2)


async def test_student_profile_does_not_expose_note(application, patient):
    application.dependency_overrides[get_current_user] = lambda: patient
    response = await send(application, None, "GET", "/users/user")
    assert response.status_code == 200
    assert "note" not in response.json()
    assert "note_version" not in response.json()
    assert "note" not in UserFullResponse.model_fields
    assert "note" not in UserUpdateRequest.model_validate({"note": "Попытка правки"}).model_dump()
    assert "psychologist_comment" not in AppointmentBase.model_fields


def test_openapi_contract_and_authentication(application):
    schema = application.openapi()
    for path, method, codes in [
        ("/medical-records/", "get", {"200", "401", "403"}),
        ("/medical-records/{user_id}", "get", {"200", "401", "403", "404", "422"}),
        ("/medical-records/{user_id}/note", "patch", {"200", "401", "403", "404", "409", "422"}),
    ]:
        operation = schema["paths"][path][method]
        assert set(operation["responses"]) == codes
        assert operation["security"] == [{"cookieAuth": []}]
    record = schema["components"]["schemas"]["MedicalRecordResponse"]
    for name in ("note_version", "tests_count", "surveys_count"):
        assert record["properties"][name]["minimum"] == 0
    assert "psychologist_comment" in schema["components"]["schemas"]["MedicalAppointment"]["properties"]
