class PatientNotFoundException(Exception):
    def __init__(self, patient_id):
        self.patient_id = patient_id
        super().__init__(f"Пациент с ID {patient_id} не найден")


class PsychologistNotFoundException(Exception):
    def __init__(self, psychologist_id):
        self.psychologist_id = psychologist_id
        super().__init__(f"Психолог с ID {psychologist_id} не найден")


class VenueRequiredException(Exception):
    def __init__(self):
        super().__init__("Место для онлайн встречи не указано")


class InvalidScheduledTimeException(Exception):
    def __init__(self, scheduled_time):
        self.scheduled_time = scheduled_time
        super().__init__(f"Время записи {scheduled_time} не может быть в прошлом")


class InvalidRemindTimeException(Exception):
    def __init__(self, remind_time, reason: str):
        self.remind_time = remind_time
        self.reason = reason
        super().__init__(f"Некорректное время напоминания {remind_time}: {reason}")


class AppointmentNotFoundException(Exception):
    def __init__(self, appointment_id):
        self.appointment_id = appointment_id
        super().__init__(f"Запись на прием с ID {appointment_id} не найдена")


class AppointmentAlreadyCancelledException(Exception):
    def __init__(self, appointment_id):
        self.appointment_id = appointment_id
        super().__init__(f"Запись на прием с ID {appointment_id} уже отменена")


class ApplicationNotFoundException(Exception):
    def __init__(self, application_id):
        self.application_id = application_id
        super().__init__(f"Заявка с ID {application_id} не найдена")

class PsychologistUnavailableException(Exception):
    def __init__(self, psychologist_id, scheduled_time):
        self.psychologist_id = psychologist_id
        self.scheduled_time = scheduled_time
        super().__init__(f"Психолог с ID {psychologist_id} недоступен в {scheduled_time}")