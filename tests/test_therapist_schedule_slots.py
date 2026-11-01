from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from psychohelp.routes.controllers import therapists


class FakeSession:
    def __init__(self, psychologist, appointments):
        self.psychologist = psychologist
        self.appointments = appointments

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, _model, _psychologist_id):
        return self.psychologist

    async def execute(self, _query):
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: self.appointments),
        )


@pytest.mark.asyncio
async def test_schedule_does_not_return_an_appointment_slot(monkeypatch):
    psychologist_id = uuid4()
    moscow_timezone = timezone(timedelta(hours=3))
    booked_time = datetime(2030, 1, 1, 10, 0, tzinfo=moscow_timezone)
    session = FakeSession(
        psychologist=SimpleNamespace(id=psychologist_id, office="101"),
        appointments=[SimpleNamespace(scheduled_time=booked_time)],
    )
    monkeypatch.setattr(therapists, "get_async_db", lambda: session)

    result = await therapists.get_psychologist_schedule(
        psychologist_id,
        date="2030-01-01",
        duration=60,
    )

    returned_times = {slot.datetime for slot in result.available_slots}
    assert booked_time.isoformat() not in returned_times
    assert datetime(2030, 1, 1, 12, 0, tzinfo=moscow_timezone).isoformat() in returned_times
