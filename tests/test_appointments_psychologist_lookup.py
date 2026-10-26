from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from psychohelp.models.appointments import AppointmentType
from psychohelp.services.appointments import appointments as appointments_service


async def test_create_appointment_accepts_psychologist_user_id(monkeypatch):
    patient_id = uuid4()
    psychologist_user_id = uuid4()
    psychologist = SimpleNamespace(id=uuid4(), office="Office 101")
    saved = SimpleNamespace(id=uuid4(), psychologist_id=psychologist.id, venue=psychologist.office)
    create = AsyncMock(return_value=saved)
    monkeypatch.setattr(appointments_service, "get_user_by_id", AsyncMock(return_value=SimpleNamespace(id=patient_id)))
    monkeypatch.setattr(appointments_service, "get_psychologist_by_id", AsyncMock(return_value=None))
    lookup = AsyncMock(return_value=psychologist)
    monkeypatch.setattr(appointments_service, "get_psychologist_by_user_id", lookup)
    monkeypatch.setattr(appointments_service, "check_psychologist_availability", AsyncMock(return_value=True))
    monkeypatch.setattr(appointments_service, "repo_create_appointment", create)
    monkeypatch.setattr(appointments_service, "repo_get_appointment_by_id", AsyncMock(return_value=saved))

    result = await appointments_service.create_appointment(
        patient_id=patient_id,
        psychologist_id=psychologist_user_id,
        type=AppointmentType.Offline,
        scheduled_time=datetime.now(timezone.utc) + timedelta(hours=2),
    )

    lookup.assert_awaited_once_with(psychologist_user_id)
    assert result.psychologist_id == psychologist.id
    assert create.call_args.kwargs["psychologist_id"] == psychologist.id
    assert create.call_args.kwargs["venue"] == "Office 101"


async def test_direct_creation_cannot_bypass_application_confirmation(monkeypatch):
    create = AsyncMock()
    monkeypatch.setattr(appointments_service, "repo_create_appointment", create)
    with pytest.raises(ValueError, match="/confirm"):
        await appointments_service.create_appointment(
            patient_id=uuid4(),
            psychologist_id=uuid4(),
            type=AppointmentType.Offline,
            scheduled_time=datetime.now(timezone.utc) + timedelta(hours=2),
            application_id=uuid4(),
        )
    create.assert_not_awaited()
