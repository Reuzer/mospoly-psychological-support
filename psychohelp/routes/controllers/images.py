from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from mimetypes import guess_type
from pathlib import Path

import os

router = APIRouter(tags=["images"])

IMAGE_DIR = os.getenv("IMAGE_DIR", "/srv/images")


EXTENSIONS_WHITE_LIST = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico"}


@router.get(
    "/image/{filename}",
    summary="Получить изображение",
    description=(
        "Возвращает файл изображения по имени из настроенного каталога изображений. Допускаются "
        "только поддерживаемые расширения; если файл не найден, возвращает 404."
    ),
)
async def get_dynamic_image(filename: str):
    """
    Получить изображение по имени файла.
    """

    # базовая проверка на подозрительные символы
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Недопустимое имя файла")
    
    # проверка расширения файла
    file_extension = Path(filename).suffix.lower()
    if file_extension not in EXTENSIONS_WHITE_LIST:
        raise HTTPException(status_code=400, detail="Недопустимый тип файла")
    
    # используем только базовое имя файла (без пути)
    safe_filename = os.path.basename(filename)
    
    # создаем безопасный путь
    base_dir = Path(IMAGE_DIR).resolve()
    
    try:
        file_path = (base_dir / safe_filename).resolve()
    except ValueError as e:
        # обработка null bytes и других недопустимых символов
        raise HTTPException(status_code=400, detail="Недопустимые символы в имени файла")
    
    try:
        file_path.relative_to(base_dir)
    except ValueError:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    # проверка существования файла
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")
    
    # определение MIME типа
    media_type = guess_type(str(file_path))[0] or "application/octet-stream"
    
    return FileResponse(file_path, media_type=media_type)
