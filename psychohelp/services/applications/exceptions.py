class ApplicationError(Exception):
    pass

class InvalidStatusTransitionError(ApplicationError):
    pass

class AccessDeniedError(ApplicationError):
    pass

class ConflictError(ApplicationError):
    pass

class ValidationError(ApplicationError):
    pass

class ApplicationNotFoundError(ApplicationError):
    pass