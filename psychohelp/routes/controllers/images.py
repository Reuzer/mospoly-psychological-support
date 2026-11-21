import os
from pathlib import Path
from mimetypes import guess_type

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(tags=["images"])

# Директория с изображениями (берется из переменной окружения или по умолчанию)
IMAGE_DIR = os.getenv("IMAGE_DIR", "/srv/images")

# Разрешенные расширения
EXTENSIONS_WHITE_LIST = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico"}


@router.get(
    "/image/{filename}",
    summary="Получить изображение",
    description=(
        "Возвращает файл изображения по имени из настроенного каталога изображений. "
        "Допускаются только поддерживаемые расширения; если файл не найден, возвращает 404."
    )
)
async def get_dynamic_image(filename: str):
    """Получить изображение по имени файла."""
    
    # 1. Базовая проверка на подозрительные символы (защита от Path Traversal)
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Недопустимое имя файла")

    # 2. Проверка расширения файла
    file_extension = Path(filename).suffix.lower()
    if file_extension not in EXTENSIONS_WHITE_LIST:
        raise HTTPException(status_code=400, detail="Недопустимый тип файла")

    # 3. Используем только базовое имя файла (без пути)
    safe_filename = os.path.basename(filename)

    # 4. Создаем безопасный путь
    base_dir = Path(IMAGE_DIR).resolve()

    try:
        file_path = (base_dir / safe_filename).resolve()
    except (ValueError, RuntimeError) as e:
        # Обработка null bytes и других недопустимых символов
        raise HTTPException(status_code=400, detail="Недопустимые символы в имени файла")

    # 5. Проверка, что итоговый путь находится внутри base_dir (защита от симлинков)
    # Используем is_relative_to для Python 3.9+, для более старых версий нужен другой подход
    try:
        file_path.relative_to(base_dir)
    except ValueError:
        raise HTTPException(status_code=403, detail="Доступ запрещен")

    # 6. Проверка существования файла
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")

    # 7. Определение MIME типа
    media_type = guess_type(str(file_path))[0] or "application/octet-stream"

    # 8. Возврат файла
    return FileResponse(
        file_path,
        media_type=media_type,
        headers={"X-Content-Type-Options": "nosniff"}
    )
