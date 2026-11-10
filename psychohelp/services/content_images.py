import io
import re
import tempfile
import warnings
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

from psychohelp.config.logging import get_logger

logger = get_logger(__name__)

MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_IMAGE_DIMENSION = 10_000
IMAGE_FILENAME = re.compile(r"[0-9a-f]{32}_[0-9a-f]{32}\.webp")
IMAGE_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


def content_image_root_path(
    image_url: str | None,
    root_path: str,
    *,
    url_prefix: str,
    add: bool,
    origin: str | None = None,
) -> str | None:
    """Учитываем root_path только для сгенерированных файлов текущего API."""
    if not image_url:
        return image_url
    try:
        parts = urlsplit(image_url)
        if parts.scheme or parts.netloc:
            if add or origin is None:
                return image_url
            api = urlsplit(origin)
            scheme = parts.scheme or api.scheme
            default_ports = {"http": 80, "https": 443}
            image_port = parts.port if parts.port is not None else default_ports.get(scheme)
            api_port = api.port if api.port is not None else default_ports.get(api.scheme)
            if (scheme, parts.hostname, image_port) != (api.scheme, api.hostname, api_port):
                return image_url
    except ValueError:
        # Старые и внешние ссылки не обязаны соответствовать формату локального URL.
        return image_url

    prefix = url_prefix if add else root_path + url_prefix
    filename = parts.path.removeprefix(prefix)
    if not parts.path.startswith(prefix) or not IMAGE_FILENAME.fullmatch(filename):
        return image_url
    path = root_path + parts.path if add else url_prefix + filename
    return urlunsplit(("", "", path, parts.query, parts.fragment))


def content_image_filename(image_url: str | None, *, url_prefix: str) -> str | None:
    """Определяем локальный файл независимо от query-параметров и фрагмента."""
    if not image_url:
        return None
    try:
        parts = urlsplit(image_url)
    except ValueError:
        return None
    if parts.scheme or parts.netloc or not parts.path.startswith(url_prefix):
        return None
    filename = parts.path.removeprefix(url_prefix)
    return filename if IMAGE_FILENAME.fullmatch(filename) else None


def save_content_image(
    owner_id: UUID,
    contents: bytes,
    content_type: str | None,
    *,
    directory: Path,
    url_prefix: str,
    max_pixels: int = MAX_IMAGE_PIXELS,
    max_dimension: int = MAX_IMAGE_DIMENSION,
) -> str:
    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(413, "Размер фотографии не должен превышать 10 МБ")
    if content_type not in IMAGE_TYPES.values():
        raise HTTPException(415, "Поддерживаются только JPEG, PNG и WebP")
    if not contents:
        raise HTTPException(400, "Файл изображения пуст")

    # Проверяем содержимое файла независимо от переданных клиентом имени и Content-Type
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(contents)) as source:
                if source.format not in IMAGE_TYPES:
                    raise HTTPException(415, "Поддерживаются только JPEG, PNG и WebP")
                if IMAGE_TYPES[source.format] != content_type:
                    raise HTTPException(400, "Тип файла не соответствует содержимому")
                if (
                    source.width * source.height > max_pixels
                    or max(source.size) > max_dimension
                ):
                    raise HTTPException(400, "Слишком большое разрешение изображения")
                if getattr(source, "n_frames", 1) != 1:
                    raise HTTPException(400, "Анимированные изображения не поддерживаются")
                source.verify()
            with Image.open(io.BytesIO(contents)) as source:
                source.load()
                oriented = ImageOps.exif_transpose(source)
                try:
                    has_alpha = "A" in oriented.getbands() or "transparency" in oriented.info
                    image = oriented.convert("RGBA" if has_alpha else "RGB")
                finally:
                    oriented.close()
                image.info.clear()
    except (
        UnidentifiedImageError, OSError, ValueError, SyntaxError,
        Image.DecompressionBombError, Image.DecompressionBombWarning,
    ) as exc:
        raise HTTPException(400, "Файл поврежден или не является допустимым изображением") from exc

    # Публикуем только заново закодированные пиксели, удаляя исходные метаданные и дописанные данные
    filename = f"{owner_id.hex}_{uuid4().hex}.webp"
    temp_path = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory, suffix=".tmp", delete=False) as temp:
            temp_path = Path(temp.name)
            image.save(temp, "WEBP", quality=90)
            temp.flush()
        # Уникальное публичное имя становится доступно только после полной записи файла
        temp_path.replace(directory / filename)
    except OSError as exc:
        logger.exception("Could not store content image for %s", owner_id)
        raise HTTPException(500, "Не удалось сохранить фотографию") from exc
    finally:
        image.close()
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Could not remove temporary image for %s", owner_id)

    return url_prefix + filename


def remove_content_image(
    owner_id: UUID, image_url: str | None, *, directory: Path, url_prefix: str,
) -> None:
    """Удаляем только сгенерированный файл, принадлежащий указанной записи."""
    filename = content_image_filename(image_url, url_prefix=url_prefix)
    if filename is None or not filename.startswith(f"{owner_id.hex}_"):
        return
    try:
        # unlink удаляет саму символьную ссылку, а не её цель за пределами хранилища
        (directory / filename).unlink(missing_ok=True)
    except OSError:
        logger.exception("Could not remove content image for %s", owner_id)
