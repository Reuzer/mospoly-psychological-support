from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from psychohelp.models.appointments import AppointmentType
from psychohelp.services.appointments import appointments as appointments_service
from psychohelp.services.appointments.exceptions import AppointmentSlotOccupiedException


@pytest.mark.asyncio
async def test_create_appointment_accepts_psychologist_user_id(monkeypatch):
    patient_id = uuid4()
    psychologist_user_id = uuid4()
    psychologist_entity_id = uuid4()
    created = SimpleNamespace(id=uuid4())
    captured = {}

    async def fake_get_user_by_id(user_id):
        return SimpleNamespace(id=patient_id) if user_id == patient_id else None

    async def fake_get_psychologist_by_id(_psychologist_id):
        return None

    async def fake_get_psychologist_by_user_id(user_id):
        if user_id == psychologist_user_id:
            return SimpleNamespace(id=psychologist_entity_id, office="Office 101")
        return None

    async def fake_available(_psychologist_id, _scheduled_time):
        return True

    async def fake_slot_available(_psychologist_id, _scheduled_time):
        return True

    async def fake_repo_create_appointment(**kwargs):
        captured.update(kwargs)
        return created

    async def fake_get_appointment(_appointment_id, _patient_id):
        return SimpleNamespace(id=created.id, **captured)

    monkeypatch.setattr(appointments_service, "get_user_by_id", fake_get_user_by_id)
    monkeypatch.setattr(appointments_service, "get_psychologist_by_id", fake_get_psychologist_by_id)
    monkeypatch.setattr(appointments_service, "get_psychologist_by_user_id", fake_get_psychologist_by_user_id)
    monkeypatch.setattr(appointments_service, "check_psychologist_availability", fake_available)
    monkeypatch.setattr(appointments_service, "is_appointment_slot_available", fake_slot_available)
    monkeypatch.setattr(appointments_service, "repo_create_appointment", fake_repo_create_appointment)
    monkeypatch.setattr(appointments_service, "repo_get_appointment_by_id", fake_get_appointment)

    appointment = await appointments_service.create_appointment(
        patient_id=patient_id,
        psychologist_id=psychologist_user_id,
        type=AppointmentType.Offline,
        duration=90,
        scheduled_time=datetime.now(timezone.utc) + timedelta(hours=2),
        reason="test",
    )

    assert appointment.psychologist_id == psychologist_entity_id
    assert appointment.patient_id == patient_id
    assert appointment.venue == "Office 101"
    assert appointment.duration == 90


@pytest.mark.asyncio
async def test_create_appointment_rejects_occupied_slot(monkeypatch):
    patient_id = uuid4()
    psychologist_id = uuid4()

    async def fake_get_user_by_id(_user_id):
        return SimpleNamespace(id=patient_id)

    async def fake_get_psychologist_by_id(_psychologist_id):
        return SimpleNamespace(id=psychologist_id, office="Office 101")

    async def fake_available(_psychologist_id, _scheduled_time):
        return True

    async def fake_slot_available(_psychologist_id, _scheduled_time):
        return False

    async def fail_create(**_kwargs):
        raise AssertionError("occupied slot must not be persisted")

    monkeypatch.setattr(appointments_service, "get_user_by_id", fake_get_user_by_id)
    monkeypatch.setattr(appointments_service, "get_psychologist_by_id", fake_get_psychologist_by_id)
    monkeypatch.setattr(appointments_service, "check_psychologist_availability", fake_available)
    monkeypatch.setattr(appointments_service, "is_appointment_slot_available", fake_slot_available)
    monkeypatch.setattr(appointments_service, "repo_create_appointment", fail_create)

    with pytest.raises(AppointmentSlotOccupiedException):
        await appointments_service.create_appointment(
            patient_id=patient_id,
            psychologist_id=psychologist_id,
            type=AppointmentType.Offline,
            scheduled_time=datetime.now(timezone.utc) + timedelta(hours=2),
        )
