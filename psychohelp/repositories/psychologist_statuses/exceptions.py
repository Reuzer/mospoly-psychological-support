class OverlappingStatusException(Exception):
    def __init__(self, psychologist_id):
        self.psychologist_id = psychologist_id
        super().__init__(f"Psychologist with ID {psychologist_id} has overlapping status")

class InvalidStatusPeriodException(Exception):
    def __init__(self, psychologist_id):
        self.psychologist_id = psychologist_id
        super().__init__(f"Psychologist with ID {psychologist_id} has an invalid status period")

class PsychologistStatusNotFoundException(Exception):
    def __init__(self, psychologist_id):
        self.psychologist_id = psychologist_id
        super().__init__(f"Psychologist with ID {psychologist_id} has no status found")