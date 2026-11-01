from types import SimpleNamespace
from uuid import uuid4

import pytest

from psychohelp.models.appointments import AppointmentStatus
from psychohelp.repositories import appointments as appointments_repo


class FakeResult:
    def __init__(self, appointment):
        self.appointment = appointment

    def scalar_one_or_none(self):
        return self.appointment


class FakeSession:
    def __init__(self, appointment):
        self.appointment = appointment
        self.committed = False

    async def execute(self, _query):
        return FakeResult(self.appointment)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass


class FakeDb:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def make_appointment():
    return SimpleNamespace(
        patient_id=uuid4(),
        psychologist=SimpleNamespace(user_id=uuid4()),
        status=AppointmentStatus.awaiting,
        cancel_reason=None,
        cancelled_by=None,
        emergency_cancellation=False,
        last_change_time=None,
    )


@pytest.mark.asyncio
async def test_patient_can_cancel_appointment(monkeypatch):
    appointment = make_appointment()
    session = FakeSession(appointment)
    monkeypatch.setattr(appointments_repo, "get_async_db", lambda: FakeDb(session))

    result = await appointments_repo.cancel_appointment_by_id(
        uuid4(),
        appointment.patient_id,
        "Не смогу прийти",
    )

    assert result.status == AppointmentStatus.cancelled
    assert result.cancelled_by == "patient"
    assert result.emergency_cancellation is False
    assert session.committed is True


@pytest.mark.asyncio
async def test_psychologist_cannot_cancel_without_emergency(monkeypatch):
    appointment = make_appointment()
    session = FakeSession(appointment)
    monkeypatch.setattr(appointments_repo, "get_async_db", lambda: FakeDb(session))

    with pytest.raises(PermissionError, match="только при ЧС"):
        await appointments_repo.cancel_appointment_by_id(
            uuid4(),
            appointment.psychologist.user_id,
            "Неудобное время",
        )

    assert appointment.status == AppointmentStatus.awaiting
    assert session.committed is False


@pytest.mark.asyncio
async def test_psychologist_can_cancel_in_emergency(monkeypatch):
    appointment = make_appointment()
    session = FakeSession(appointment)
    monkeypatch.setattr(appointments_repo, "get_async_db", lambda: FakeDb(session))

    result = await appointments_repo.cancel_appointment_by_id(
        uuid4(),
        appointment.psychologist.user_id,
        "Экстренная ситуация",
        is_emergency=True,
    )

    assert result.status == AppointmentStatus.cancelled
    assert result.cancelled_by == "psychologist"
    assert result.emergency_cancellation is True
    assert session.committed is True
