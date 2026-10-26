from datetime import datetime, timezone
from uuid import UUID
from typing import Optional
from psychohelp.repositories import applications as repo
from psychohelp.services.applications.exceptions import (
    InvalidStatusTransitionError,
    AccessDeniedError,
    ConflictError,
    ValidationError,
    ApplicationNotFoundError
)
from psychohelp.services.audit import log_application_status_change
from psychohelp.models.applications import Application, ApplicationStatus, CancelInitiator


class ApplicationStateMachine:
    def __init__(self, application: Application):
        self.application = application

    def _check_not_final(self):
        final_statuses = {
            ApplicationStatus.COMPLETED,
            ApplicationStatus.REJECTED,
            ApplicationStatus.CANCELLED,
            ApplicationStatus.EXPIRED
        }
        if self.application.status in final_statuses:
            raise InvalidStatusTransitionError(f"Заявка в финальном статусе {self.application.status}, переход невозможен")
        
    async def _transition(self, new_status: str, update_data: dict, actor_id: UUID, actor_type: str, comment: str = None):
        self._check_not_final()
        update_data["status"] = new_status
        update_data["updated_at"] = datetime.now(timezone.utc)
        # optimistic locking
        updated = await repo.update_application_with_version(
            self.application.id,
            self.application.version,
            update_data
        )
        if not updated:
            raise ConflictError("Заявка была изменена другим пользователем, повторите операцию")
        # await log_application_status_change(
        #     application_id=self.application.id,
        #     previous_status=self.application.status,
        #     new_status=new_status,
        #     actor_type=actor_type,
        #     actor_id=actor_id,
        #     comment=comment
        # )
        return updated

    async def accept_to_processing(self, assigned_to: UUID, actor_id: UUID, actor_type: str) -> Application:
        if self.application.status != ApplicationStatus.NEW:
            raise InvalidStatusTransitionError(f"Невозможно принять в обработку из статуса {self.application.status}")
        update_data = {
            "assigned_to": assigned_to,
            "processing_started_at": datetime.now(timezone.utc)
        }
        return await self._transition(ApplicationStatus.IN_PROGRESS, update_data, actor_id, actor_type)

    async def offer_consultation(self, offer_data: dict, actor_id: UUID, actor_type: str) -> Application:
        if self.application.status not in (ApplicationStatus.IN_PROGRESS, ApplicationStatus.AWAITING_USER_CONFIRMATION):
            raise InvalidStatusTransitionError(f"Невозможно предложить консультацию из статуса {self.application.status}")
        update_data = {
            "psychologist_id": offer_data["psychologist_id"],
            "meeting_type": offer_data["meeting_type"],
            "scheduled_at": offer_data["scheduled_at"],
            "location_address": offer_data.get("location_address"),
            "meeting_url": offer_data.get("meeting_url"),
            "confirmation_requested_at": datetime.now(timezone.utc)
        }
        return await self._transition(ApplicationStatus.AWAITING_USER_CONFIRMATION, update_data, actor_id, actor_type)

    async def reassign(self, offer_data: dict, actor_id: UUID) -> Application:
        if self.application.status != ApplicationStatus.AWAITING_USER_CONFIRMATION:
            raise InvalidStatusTransitionError(
                "Переназначить заявку можно только на этапе подтверждения пользователя"
            )
        update_data = {
            "assigned_to": actor_id,
            "psychologist_id": offer_data["psychologist_id"],
            "meeting_type": offer_data["meeting_type"],
            "scheduled_at": offer_data["scheduled_at"],
            "location_address": offer_data.get("location_address"),
            "meeting_url": offer_data.get("meeting_url"),
            "confirmation_requested_at": datetime.now(timezone.utc),
        }
        return await self._transition(
            ApplicationStatus.AWAITING_USER_CONFIRMATION,
            update_data,
            actor_id,
            "psychologist",
        )

    async def confirm(self, actor_id: UUID, actor_type: str, appointment_id: UUID) -> Application:
        if self.application.status != ApplicationStatus.AWAITING_USER_CONFIRMATION:
            raise InvalidStatusTransitionError(f"Невозможно подтвердить из статуса {self.application.status}")
        if not appointment_id:
            raise ValidationError("Для завершения заявки необходимо создать запись на приём")
        update_data = {
            "appointment_id": appointment_id,
            "completed_at": datetime.now(timezone.utc)
        }
        return await self._transition(ApplicationStatus.COMPLETED, update_data, actor_id, actor_type)

    async def reject(self, reject_reason: str, actor_id: UUID, actor_type: str) -> Application:
        if self.application.status not in (ApplicationStatus.NEW, ApplicationStatus.IN_PROGRESS):
            raise InvalidStatusTransitionError(f"Невозможно отклонить из статуса {self.application.status}")
        if not reject_reason:
            raise ValidationError("Необходимо указать причину отклонения")
        update_data = {
            "reject_reason": reject_reason,
            "rejected_at": datetime.now(timezone.utc)
        }
        return await self._transition(ApplicationStatus.REJECTED, update_data, actor_id, actor_type)

    async def cancel(self, cancel_reason: str, cancel_initiator: CancelInitiator, actor_id: UUID, actor_type: str) -> Application:
        if self.application.status in (ApplicationStatus.COMPLETED, ApplicationStatus.REJECTED, ApplicationStatus.EXPIRED):
            raise InvalidStatusTransitionError(f"Невозможно отменить заявку в статусе {self.application.status}")
        if not cancel_reason:
            raise ValidationError("Необходимо указать причину отмены")
        update_data = {
            "cancel_reason": cancel_reason,
            "cancel_initiator": cancel_initiator.value,
            "cancelled_at": datetime.now(timezone.utc)
        }
        return await self._transition(ApplicationStatus.CANCELLED, update_data, actor_id, actor_type)

    async def expire(self, actor_id: UUID, actor_type: str = "system") -> Application:
        if self.application.status not in (ApplicationStatus.NEW, ApplicationStatus.IN_PROGRESS, ApplicationStatus.AWAITING_USER_CONFIRMATION):
            raise InvalidStatusTransitionError(f"Невозможно перевести в expired из статуса {self.application.status}")
        update_data = {"expired_at": datetime.now(timezone.utc)}
        return await self._transition(ApplicationStatus.EXPIRED, update_data, actor_id, actor_type)
