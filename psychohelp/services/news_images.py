from uuid import UUID

from psychohelp.config.config import config
from psychohelp.services.content_images import (
    IMAGE_FILENAME,
    MAX_IMAGE_DIMENSION,
    MAX_IMAGE_PIXELS,
    MAX_IMAGE_SIZE,
    remove_content_image,
    save_content_image,
)

IMAGE_URL_PREFIX = "/media/news/"


def save_news_image(news_id: UUID, contents: bytes, content_type: str | None) -> str:
    return save_content_image(
        news_id, contents, content_type,
        directory=config.NEWS_IMAGE_DIR, url_prefix=IMAGE_URL_PREFIX,
        max_pixels=MAX_IMAGE_PIXELS, max_dimension=MAX_IMAGE_DIMENSION,
    )


def remove_news_image(news_id: UUID, image_url: str | None) -> None:
    remove_content_image(
        news_id, image_url,
        directory=config.NEWS_IMAGE_DIR, url_prefix=IMAGE_URL_PREFIX,
    )
