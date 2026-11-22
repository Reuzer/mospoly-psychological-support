from uuid import UUID


class MedicalRecordNotFoundException(Exception):
    def __init__(self, user_id: UUID):
        self.user_id = user_id
        super().__init__("Медкарта пациента не найдена")


class MedicalRecordNoteVersionConflict(Exception):
    def __init__(self):
        super().__init__("Заметка уже изменена другим специалистом. Обновите медкарту")
