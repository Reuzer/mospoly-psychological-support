"""Общие схемы фактических ошибок API для OpenAPI."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str


class ValidationIssue(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class RegistrationValidationErrorResponse(BaseModel):
    # Регистрация возвращает также бизнес-ошибки с текстовым detail.
    detail: str | list[ValidationIssue]


class RateLimitErrorResponse(BaseModel):
    error: str


ERROR_DESCRIPTIONS = {
    400: "Недопустимые условия операции",
    401: "Пользователь не авторизован или токен недействителен",
    403: "Недостаточно прав для выполнения операции",
    404: "Запрашиваемый объект не найден",
    409: "Конфликт состояния или версии объекта",
    422: "Ошибка валидации входных данных",
    429: "Превышено допустимое количество запросов",
    500: "Внутренняя ошибка сервера",
}


def error_responses(*codes: int) -> dict:
    """Описывает только ошибки, предусмотренные конкретным методом."""
    return {
        code: {
            "model": (
                RateLimitErrorResponse if code == 429
                else RegistrationValidationErrorResponse if code == 422
                else ErrorResponse
            ),
            "description": ERROR_DESCRIPTIONS[code],
            "content": {
                "application/json": {
                    "example": {
                        "error" if code == 429 else "detail": ERROR_DESCRIPTIONS[code],
                    },
                },
            },
        }
        for code in codes
    }
