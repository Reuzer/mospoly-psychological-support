from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from psychohelp.dependencies.auth import get_current_user, get_optional_user
from psychohelp.models.appointments import AppointmentStatus, AppointmentType
from psychohelp.repositories import appointments as repository
from psychohelp.routes.controllers import appointments as controller
from psychohelp.schemas.applications import AppointmentFullResponse
from psychohelp.services.rbac import permissions


def make_appointment():
    def user():
        return SimpleNamespace(
            id=uuid4(), first_name="Анна", last_name="Иванова", phone_number="+79991234567",
            email="anna@example.com",
        )

    patient, psychologist_user = user(), user()
    psychologist = SimpleNamespace(
        id=uuid4(), user_id=psychologist_user.id, user=psychologist_user,
        experience="1", qualification="Психолог", consult_areas="Учёба", description="Описание",
        office="101", education="Высшее", short_description="Психолог",
    )
    return SimpleNamespace(
        id=uuid4(), patient_id=patient.id, patient=patient, psychologist=psychologist,
        psychologist_id=psychologist.id, status=AppointmentStatus.awaiting,
        type=AppointmentType.Offline, scheduled_time=datetime.now(timezone.utc) - timedelta(days=1),
        venue="101", comment="Исходный комментарий", emergency_contact="Старый контакт",
        last_change_time=datetime.now(timezone.utc) - timedelta(days=2),
    )


@pytest.fixture
def api(monkeypatch):
    appointment = make_appointment()
    state = SimpleNamespace(appointment=appointment, actor=appointment.patient, commits=0)

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def execute(self, _query):
            return SimpleNamespace(
                scalar_one_or_none=lambda: state.appointment,
                scalars=lambda: SimpleNamespace(all=lambda: [state.appointment]),
            )

        async def commit(self):
            state.commits += 1

    monkeypatch.setattr(repository, "get_async_db", Session)
    monkeypatch.setattr(permissions, "user_has_permission", AsyncMock(return_value=True))
    app = FastAPI()
    app.include_router(controller.router)
    app.dependency_overrides[get_current_user] = lambda: state.actor
    app.dependency_overrides[get_optional_user] = lambda: state.actor
    state.app = app
    return state


@pytest.mark.parametrize("actor", ["patient", "psychologist"])
@pytest.mark.parametrize("value, expected", [
    ("  Анна, мама, +79991234567  ", "Анна, мама, +79991234567"),
    (None, None), ("", None), (" \t\n ", None), (" " + "я" * 512 + " ", "я" * 512),
])
async def test_members_update_and_read_contact(api, actor, value, expected):
    appointment = api.appointment
    before = vars(appointment).copy()
    if actor == "psychologist":
        api.actor = appointment.psychologist.user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://test") as client:
        response = await client.patch(
            f"/appointments/{appointment.id}/emergency-contact", json={"emergency_contact": value},
        )
        assert response.status_code == 200, response.text
        assert response.json()["emergency_contact"] == expected
        assert (await client.get(f"/appointments/{appointment.id}")).json()["emergency_contact"] == expected
        assert (await client.get("/appointments/")).json()[0]["emergency_contact"] == expected

    assert api.commits == 1
    assert appointment.last_change_time > before["last_change_time"]
    assert appointment.last_change_time.tzinfo == timezone.utc
    for key, value in before.items():
        if key not in {"emergency_contact", "last_change_time"}:
            assert getattr(appointment, key) == value


@pytest.mark.parametrize("actor", ["student", "psychologist", "admin", "psychologist_entity_id"])
@pytest.mark.parametrize("status", list(AppointmentStatus))
async def test_nonmembers_cannot_update_even_closed_appointments(api, actor, status):
    api.appointment.status = status
    actor_id = api.appointment.psychologist_id if actor == "psychologist_entity_id" else uuid4()
    api.actor = SimpleNamespace(id=actor_id, role=actor, is_admin=actor == "admin")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://test") as client:
        response = await client.patch(
            f"/appointments/{api.appointment.id}/emergency-contact", json={"emergency_contact": "Контакт"},
        )
    assert response.status_code == 404
    assert api.commits == 0
    assert api.appointment.emergency_contact == "Старый контакт"


@pytest.mark.parametrize("status", [AppointmentStatus.done, AppointmentStatus.cancelled])
@pytest.mark.parametrize("actor", ["patient", "psychologist"])
async def test_closed_appointment_cannot_be_changed(api, status, actor):
    api.appointment.status = status
    if actor == "psychologist":
        api.actor = api.appointment.psychologist.user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://test") as client:
        response = await client.patch(
            f"/appointments/{api.appointment.id}/emergency-contact", json={"emergency_contact": None},
        )
        assert response.status_code == 409
        assert (await client.get(f"/appointments/{api.appointment.id}")).json()["emergency_contact"] == "Старый контакт"
    assert api.commits == 0


@pytest.mark.parametrize("payload", [
    {}, {"emergency_contact": "я" * 513}, {"emergency_contact": 123},
    {"emergency_contact": False}, {"emergency_contact": []}, {"emergency_contact": {}},
    {"emergency_contact": None, "status": "done"},
])
async def test_invalid_payload_is_rejected(api, payload):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://test") as client:
        response = await client.patch(f"/appointments/{api.appointment.id}/emergency-contact", json=payload)
    assert response.status_code == 422
    assert api.commits == 0


async def test_missing_appointment(api):
    api.appointment = None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://test") as client:
        response = await client.patch(f"/appointments/{uuid4()}/emergency-contact", json={"emergency_contact": None})
    assert response.status_code == 404
    assert api.commits == 0


async def test_invalid_uuid(api):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://test") as client:
        response = await client.patch("/appointments/invalid/emergency-contact", json={"emergency_contact": None})
    assert response.status_code == 422
    assert api.commits == 0


async def test_authentication_required(api):
    api.app.dependency_overrides.pop(get_current_user)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://test") as client:
        response = await client.patch(f"/appointments/{uuid4()}/emergency-contact", json={"emergency_contact": None})
    assert response.status_code == 401
    assert api.commits == 0


def test_contact_is_not_exposed_in_application_schema():
    assert "emergency_contact" not in AppointmentFullResponse.model_fields
