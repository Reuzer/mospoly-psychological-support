from fastapi import HTTPException, Request
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartException

from psychohelp.services.article_images import MAX_IMAGE_SIZE

MAX_IMAGE_REQUEST_SIZE = MAX_IMAGE_SIZE + 64 * 1024  # Файл, заголовки и разделители формы


class ArticleImageUploadRoute(APIRoute):
    def get_route_handler(self):
        original_handler = super().get_route_handler()
        if "POST" not in self.methods or not self.path.endswith("/{article_id}/image"):
            return original_handler

        async def limited_handler(request: Request):
            content_length = request.headers.get("content-length")
            if content_length is not None:
                if not content_length.isascii() or not content_length.isdecimal():
                    raise HTTPException(400, "Недопустимый Content-Length")
                # Сравниваем нормализованные строки цифр, чтобы безопасно обработать даже очень длинный заголовок
                normalized_length = content_length.lstrip("0") or "0"
                maximum = str(MAX_IMAGE_REQUEST_SIZE)
                if len(normalized_length) > len(maximum) or (
                    len(normalized_length) == len(maximum) and normalized_length > maximum
                ):
                    raise HTTPException(413, "Размер запроса загрузки фотографии превышен")

            received = 0
            exceeded = False

            async def limited_receive():
                nonlocal received, exceeded
                message = await request.receive()
                if message["type"] == "http.request":
                    received += len(message.get("body", b""))
                    if received > MAX_IMAGE_REQUEST_SIZE:
                        exceeded = True
                        # При этом исключении обработчик формы закрывает свои временные файлы
                        raise MultiPartException("Размер запроса загрузки фотографии превышен")
                return message

            try:
                return await original_handler(Request(request.scope, receive=limited_receive))
            except StarletteHTTPException as exc:
                if exceeded:
                    raise HTTPException(413, "Размер запроса загрузки фотографии превышен") from exc
                raise

        return limited_handler
