from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from unittest.mock import AsyncMock

from psychohelp.models.applications import ApplicationStatus
from psychohelp.schemas.applications import MeetingType, OfferConsultationRequest
from psychohelp.services.applications import applications as applications_service
from psychohelp.services.applications.exceptions import ValidationError


@pytest.mark.asyncio
async def test_offer_consultation_accepts_psychologist_user_id(monkeypatch):
    application_id = uuid4()
    actor_id = uuid4()
    psychologist_user_id = uuid4()
    psychologist_entity_id = uuid4()

    offer_data = OfferConsultationRequest(
        psychologist_id=psychologist_user_id,
        meeting_type=MeetingType.OFFLINE,
        scheduled_at=datetime.now(timezone.utc) + timedelta(hours=2),
        location_address="cabinet",
    )

    fake_application = SimpleNamespace(id=application_id, status=ApplicationStatus.IN_PROGRESS, version=1)

    async def fake_get_application_by_id(actual_application_id):
        assert actual_application_id == application_id
        return fake_application

    async def fake_get_psychologist_by_id(psychologist_id):
        assert psychologist_id == psychologist_user_id
        return None

    async def fake_get_psychologist_by_user_id(user_id):
        assert user_id == psychologist_user_id
        return SimpleNamespace(id=psychologist_entity_id)

    class FakeStateMachine:
        def __init__(self, application):
            self.application = application

        async def offer_consultation(self, payload, actual_actor_id, actor_type):
            assert payload["psychologist_id"] == psychologist_entity_id
            assert actual_actor_id == actor_id
            assert actor_type == "psychologist"
            fake_application.status = ApplicationStatus.AWAITING_USER_CONFIRMATION
            return fake_application

    monkeypatch.setattr(applications_service.repo, "get_application_by_id", fake_get_application_by_id)
    monkeypatch.setattr(applications_service, "get_psychologist_by_id", fake_get_psychologist_by_id)
    monkeypatch.setattr(applications_service, "get_psychologist_by_user_id", fake_get_psychologist_by_user_id)
    monkeypatch.setattr(applications_service, "ApplicationStateMachine", FakeStateMachine)

    monkeypatch.setattr(applications_service, "check_psychologist_availability", AsyncMock(return_value=True))

    result = await applications_service.offer_consultation(application_id, offer_data, actor_id, is_psychologist=True)

    assert result.status == ApplicationStatus.AWAITING_USER_CONFIRMATION


@pytest.mark.asyncio
async def test_offer_consultation_raises_validation_when_psychologist_not_found(monkeypatch):
    application_id = uuid4()
    actor_id = uuid4()
    psychologist_user_id = uuid4()

    offer_data = OfferConsultationRequest(
        psychologist_id=psychologist_user_id,
        meeting_type=MeetingType.ONLINE,
        scheduled_at=datetime.now(timezone.utc) + timedelta(hours=2),
        meeting_url="https://example.com/meet",
    )

    fake_application = SimpleNamespace(id=application_id, status=ApplicationStatus.IN_PROGRESS, version=1)

    async def fake_get_application_by_id(_):
        return fake_application

    async def fake_get_psychologist_by_id(_):
        return None

    async def fake_get_psychologist_by_user_id(_):
        return None

    monkeypatch.setattr(applications_service.repo, "get_application_by_id", fake_get_application_by_id)
    monkeypatch.setattr(applications_service, "get_psychologist_by_id", fake_get_psychologist_by_id)
    monkeypatch.setattr(applications_service, "get_psychologist_by_user_id", fake_get_psychologist_by_user_id)

    with pytest.raises(ValidationError, match="Психолог не найден"):
        await applications_service.offer_consultation(application_id, offer_data, actor_id, is_psychologist=True)


@pytest.mark.parametrize(("meeting_type", "terms"), [
    (MeetingType.OFFLINE, {}),
    (MeetingType.OFFLINE, {"location_address": "   "}),
    (MeetingType.OFFLINE, {"location_address": "x" * 129}),
    (MeetingType.ONLINE, {}),
    (MeetingType.ONLINE, {"meeting_url": "   "}),
    (MeetingType.ONLINE, {"meeting_url": "x" * 129}),
])
async def test_offer_rejects_conditions_that_cannot_create_an_appointment(monkeypatch, meeting_type, terms):
    application = SimpleNamespace(id=uuid4(), status=ApplicationStatus.IN_PROGRESS, version=1)
    monkeypatch.setattr(applications_service.repo, "get_application_by_id", AsyncMock(return_value=application))
    monkeypatch.setattr(applications_service, "get_psychologist_by_id", AsyncMock(return_value=SimpleNamespace(id=uuid4())))
    write = AsyncMock()
    monkeypatch.setattr(applications_service.repo, "update_application_with_version", write)
    with pytest.raises(ValidationError):
        await applications_service.offer_consultation(
            application.id,
            OfferConsultationRequest(
                psychologist_id=uuid4(), meeting_type=meeting_type,
                scheduled_at=datetime.now(timezone.utc) + timedelta(days=1), **terms,
            ),
            uuid4(), True,
        )
    write.assert_not_awaited()
    assert application.status == ApplicationStatus.IN_PROGRESS


async def test_offer_checks_psychologist_availability_before_changing_application(monkeypatch):
    application = SimpleNamespace(id=uuid4(), status=ApplicationStatus.IN_PROGRESS, version=1)
    monkeypatch.setattr(applications_service.repo, "get_application_by_id", AsyncMock(return_value=application))
    monkeypatch.setattr(applications_service, "get_psychologist_by_id", AsyncMock(return_value=SimpleNamespace(id=uuid4())))
    monkeypatch.setattr(applications_service, "check_psychologist_availability", AsyncMock(return_value=False))
    write = AsyncMock()
    monkeypatch.setattr(applications_service.repo, "update_application_with_version", write)
    with pytest.raises(ValidationError, match="отпуске или на больничном"):
        await applications_service.offer_consultation(
            application.id,
            OfferConsultationRequest(
                psychologist_id=uuid4(), meeting_type=MeetingType.OFFLINE,
                scheduled_at=datetime.now(timezone.utc) + timedelta(days=1), location_address="Кабинет 1",
            ),
            uuid4(), True,
        )
    write.assert_not_awaited()
