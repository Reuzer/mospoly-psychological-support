from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from psychohelp.models.appointment_reschedule_requests import (
    AppointmentRescheduleStatus,
)
from psychohelp.models.appointments import AppointmentStatus
from psychohelp.repositories import appointment_reschedule_requests as reschedule_repo
from psychohelp.routes.controllers import appointments as appointments_controller
from psychohelp.schemas.appointments import AppointmentRescheduleCancelRequest
from psychohelp.services.appointments import appointments as appointments_service
from psychohelp.services.appointments import exceptions as appointment_exceptions


def test_reschedule_cancel_reason_is_required():
    with pytest.raises(ValidationError):
        AppointmentRescheduleCancelRequest(rejection_comment="")


def test_cancel_and_legacy_reject_routes_are_registered():
    post_paths = {
        route.path
        for route in appointments_controller.router.routes
        if "POST" in route.methods
    }

    assert "/appointments/reschedule-requests/{request_id}/cancel" in post_paths
    assert "/appointments/reschedule-requests/{request_id}/reject" in post_paths


@pytest.mark.asyncio
async def test_request_appointment_reschedule_normalizes_and_delegates(monkeypatch):
    appointment_id = uuid4()
    psychologist_user_id = uuid4()
    scheduled_time = datetime.now(timezone.utc) + timedelta(days=1)
    remind_time = scheduled_time - timedelta(hours=1)
    captured = {}

    async def fake_create_reschedule_request(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id=uuid4())

    async def fake_get_psychologist_by_user_id(user_id):
        assert user_id == psychologist_user_id
        return SimpleNamespace(id=uuid4())

    async def fake_available(*_args):
        return True

    monkeypatch.setattr(
        appointments_service,
        "get_psychologist_by_user_id",
        fake_get_psychologist_by_user_id,
    )
    monkeypatch.setattr(
        appointments_service,
        "check_psychologist_availability",
        fake_available,
    )
    monkeypatch.setattr(
        appointments_service,
        "is_appointment_slot_available",
        fake_available,
    )

    monkeypatch.setattr(
        appointments_service.reschedule_repo,
        "create_reschedule_request",
        fake_create_reschedule_request,
    )

    result = await appointments_service.request_appointment_reschedule(
        appointment_id=appointment_id,
        psychologist_user_id=psychologist_user_id,
        scheduled_time=scheduled_time,
        remind_time=remind_time,
        venue="Кабинет 1",
        comment="Нужно перенести",
    )

    assert result.id
    assert captured["appointment_id"] == appointment_id
    assert captured["psychologist_user_id"] == psychologist_user_id
    assert captured["scheduled_time"].tzinfo == timezone.utc
    assert captured["remind_time"].tzinfo == timezone.utc
    assert captured["venue"] == "Кабинет 1"
    assert captured["comment"] == "Нужно перенести"


@pytest.mark.asyncio
async def test_request_appointment_reschedule_rejects_past_time(monkeypatch):
    async def fake_create_reschedule_request(**_kwargs):
        raise AssertionError("repository should not be called")

    monkeypatch.setattr(
        appointments_service.reschedule_repo,
        "create_reschedule_request",
        fake_create_reschedule_request,
    )

    with pytest.raises(appointment_exceptions.InvalidScheduledTimeException):
        await appointments_service.request_appointment_reschedule(
            appointment_id=uuid4(),
            psychologist_user_id=uuid4(),
            scheduled_time=datetime.now(timezone.utc) - timedelta(minutes=1),
        )


class FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self, result):
        self.result = result
        self.committed = False
        self.refreshed = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _query):
        return FakeScalarResult(self.result)

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        self.refreshed = obj


class FakeSequenceSession(FakeSession):
    def __init__(self, results):
        super().__init__(None)
        self.results = iter(results)
        self.added = None

    async def execute(self, _query):
        return FakeScalarResult(next(self.results))

    def add(self, obj):
        self.added = obj


class FakeDb:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_create_reschedule_request_keeps_appointment_unchanged(monkeypatch):
    psychologist_user_id = uuid4()
    old_time = datetime.now(timezone.utc) + timedelta(days=1)
    old_remind_time = old_time - timedelta(hours=1)
    new_time = old_time + timedelta(days=1)
    appointment = SimpleNamespace(
        id=uuid4(),
        psychologist=SimpleNamespace(user_id=psychologist_user_id),
        status=AppointmentStatus.awaiting,
        scheduled_time=old_time,
        remind_time=old_remind_time,
        venue="Старый кабинет",
        comment="Старый комментарий",
    )
    session = FakeSequenceSession([appointment, None])

    monkeypatch.setattr(reschedule_repo, "get_async_db", lambda: FakeDb(session))

    result = await reschedule_repo.create_reschedule_request(
        appointment_id=appointment.id,
        psychologist_user_id=psychologist_user_id,
        scheduled_time=new_time,
        remind_time=None,
        venue="Новый кабинет",
        comment="ЧС",
    )

    assert result is session.added
    assert session.committed is True
    assert appointment.scheduled_time == old_time
    assert appointment.remind_time == old_remind_time
    assert appointment.venue == "Старый кабинет"
    assert appointment.comment == "Старый комментарий"
    assert result.requested_scheduled_time == new_time


@pytest.mark.asyncio
async def test_create_reschedule_request_rejects_second_pending_request(monkeypatch):
    psychologist_user_id = uuid4()
    appointment = SimpleNamespace(
        id=uuid4(),
        psychologist=SimpleNamespace(user_id=psychologist_user_id),
        status=AppointmentStatus.awaiting,
    )
    session = FakeSequenceSession([appointment, SimpleNamespace(id=uuid4())])

    monkeypatch.setattr(reschedule_repo, "get_async_db", lambda: FakeDb(session))

    with pytest.raises(ValueError, match="уже запрошен перенос"):
        await reschedule_repo.create_reschedule_request(
            appointment_id=appointment.id,
            psychologist_user_id=psychologist_user_id,
            scheduled_time=datetime.now(timezone.utc) + timedelta(days=2),
            remind_time=None,
            venue=None,
            comment=None,
        )

    assert session.committed is False
    assert session.added is None


@pytest.mark.asyncio
async def test_confirm_reschedule_request_applies_changes(monkeypatch):
    patient_id = uuid4()
    new_time = datetime.now(timezone.utc) + timedelta(days=2)
    appointment = SimpleNamespace(
        patient_id=patient_id,
        status=AppointmentStatus.awaiting,
        scheduled_time=datetime.now(timezone.utc) + timedelta(days=1),
        remind_time=None,
        venue="Старый кабинет",
        comment="Старый комментарий",
        last_change_time=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    reschedule_request = SimpleNamespace(
        id=uuid4(),
        status=AppointmentRescheduleStatus.pending,
        appointment=appointment,
        requested_scheduled_time=new_time,
        requested_remind_time=None,
        requested_venue="Новый кабинет",
        requested_comment="Новый комментарий",
        responded_at=None,
    )
    session = FakeSession(reschedule_request)

    monkeypatch.setattr(reschedule_repo, "get_async_db", lambda: FakeDb(session))

    result = await reschedule_repo.confirm_reschedule_request(
        reschedule_request.id,
        patient_id,
    )

    assert result is reschedule_request
    assert session.committed is True
    assert appointment.scheduled_time == new_time
    assert appointment.venue == "Новый кабинет"
    assert appointment.comment == "Новый комментарий"
    assert reschedule_request.status == AppointmentRescheduleStatus.confirmed
    assert reschedule_request.responded_at is not None


@pytest.mark.asyncio
async def test_confirm_reschedule_request_forbids_non_patient(monkeypatch):
    appointment = SimpleNamespace(
        patient_id=uuid4(),
        status=AppointmentStatus.awaiting,
    )
    reschedule_request = SimpleNamespace(
        id=uuid4(),
        status=AppointmentRescheduleStatus.pending,
        appointment=appointment,
    )
    session = FakeSession(reschedule_request)

    monkeypatch.setattr(reschedule_repo, "get_async_db", lambda: FakeDb(session))

    with pytest.raises(PermissionError):
        await reschedule_repo.confirm_reschedule_request(
            reschedule_request.id,
            uuid4(),
        )

    assert session.committed is False


@pytest.mark.asyncio
async def test_cancel_reschedule_request_cancels_appointment(monkeypatch):
    patient_id = uuid4()
    old_time = datetime.now(timezone.utc) + timedelta(days=1)
    appointment = SimpleNamespace(
        patient_id=patient_id,
        status=AppointmentStatus.awaiting,
        scheduled_time=old_time,
        remind_time=None,
        venue="Старый кабинет",
        comment="Старый комментарий",
        cancel_reason=None,
        last_change_time=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    reschedule_request = SimpleNamespace(
        id=uuid4(),
        status=AppointmentRescheduleStatus.pending,
        appointment=appointment,
        rejection_comment=None,
        responded_at=None,
    )
    session = FakeSession(reschedule_request)

    monkeypatch.setattr(reschedule_repo, "get_async_db", lambda: FakeDb(session))

    previous_change_time = appointment.last_change_time

    result = await reschedule_repo.cancel_reschedule_request(
        reschedule_request.id,
        patient_id,
        "Не подходит время",
    )

    assert result is reschedule_request
    assert session.committed is True
    assert appointment.scheduled_time == old_time
    assert appointment.venue == "Старый кабинет"
    assert appointment.comment == "Старый комментарий"
    assert appointment.status == AppointmentStatus.cancelled
    assert appointment.cancel_reason == "Не подходит время"
    assert appointment.last_change_time > previous_change_time
    assert reschedule_request.status == AppointmentRescheduleStatus.rejected
    assert reschedule_request.rejection_comment == "Не подходит время"
    assert reschedule_request.responded_at is not None


@pytest.mark.asyncio
async def test_cancel_reschedule_request_forbids_non_patient(monkeypatch):
    appointment = SimpleNamespace(
        patient_id=uuid4(),
        status=AppointmentStatus.awaiting,
    )
    reschedule_request = SimpleNamespace(
        id=uuid4(),
        status=AppointmentRescheduleStatus.pending,
        appointment=appointment,
    )
    session = FakeSession(reschedule_request)

    monkeypatch.setattr(reschedule_repo, "get_async_db", lambda: FakeDb(session))

    with pytest.raises(PermissionError):
        await reschedule_repo.cancel_reschedule_request(
            reschedule_request.id,
            uuid4(),
            "Не подходит время",
        )

    assert session.committed is False


@pytest.mark.asyncio
async def test_cancel_reschedule_request_rejects_processed_request(monkeypatch):
    appointment = SimpleNamespace(
        patient_id=uuid4(),
        status=AppointmentStatus.awaiting,
    )
    reschedule_request = SimpleNamespace(
        id=uuid4(),
        status=AppointmentRescheduleStatus.confirmed,
        appointment=appointment,
    )
    session = FakeSession(reschedule_request)

    monkeypatch.setattr(reschedule_repo, "get_async_db", lambda: FakeDb(session))

    with pytest.raises(ValueError, match="уже обработан"):
        await reschedule_repo.cancel_reschedule_request(
            reschedule_request.id,
            appointment.patient_id,
            "Не подходит время",
        )

    assert session.committed is False


@pytest.mark.asyncio
async def test_reject_reschedule_request_is_cancel_alias(monkeypatch):
    request_id = uuid4()
    patient_id = uuid4()
    captured = {}
    expected = SimpleNamespace(id=request_id)

    async def fake_cancel_reschedule_request(**kwargs):
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(
        reschedule_repo,
        "cancel_reschedule_request",
        fake_cancel_reschedule_request,
    )

    result = await reschedule_repo.reject_reschedule_request(
        request_id,
        patient_id,
        "Не подходит время",
    )

    assert result is expected
    assert captured == {
        "request_id": request_id,
        "patient_user_id": patient_id,
        "rejection_comment": "Не подходит время",
    }
