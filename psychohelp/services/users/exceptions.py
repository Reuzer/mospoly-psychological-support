class UserNotFound(Exception):
    pass

class WrongPassword(Exception):
    pass

class InvalidToken(Exception):
    pass
class PermissionDenied(Exception):
    pass

class InvalidImageError(Exception):
    pass

class ImageProcessingError(Exception):
    pass