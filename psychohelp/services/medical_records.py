from uuid import UUID

from psychohelp.models.users import User
from psychohelp.repositories import medical_records as repo
from psychohelp.schemas.medical_records import MedicalRecordPreview, MedicalRecordResponse
from psychohelp.services.medical_record_exceptions import MedicalRecordNotFoundException


async def get_medical_record_list() -> list[MedicalRecordPreview]:
    users = await repo.get_medical_record_list()
    return [
        MedicalRecordPreview(id=user.id, user=user, note=user.note)
        for user in users
    ]


async def get_medical_record_by_user_id(user_id: UUID) -> MedicalRecordResponse:
    record = await repo.get_medical_record_by_user_id(user_id)
    if record is None:
        raise MedicalRecordNotFoundException(user_id)
    return MedicalRecordResponse.model_validate(record)


async def update_medical_record_note(
    user_id: UUID, note: str | None, note_version: int,
) -> User:
    return await repo.update_medical_record_note(user_id, note, note_version)
