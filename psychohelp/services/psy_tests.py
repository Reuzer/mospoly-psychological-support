from uuid import UUID

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from psychohelp.models.psy_tests import PsyTest
import psychohelp.repositories.psy_tests as psy_tests_repo
from psychohelp.services.psy_test_images import (
    MAX_IMAGE_SIZE,
    remove_psy_test_image,
    save_psy_test_image,
)


async def get_psy_test_list(skip: int = 0, take: int = 100) -> list[PsyTest]:
    return await psy_tests_repo.get_psy_test_list(skip, take)


async def get_psy_test_by_id(psy_test_id: UUID) -> PsyTest | None:
    return await psy_tests_repo.get_psy_test_by_id(psy_test_id)


async def create_psy_test(psy_test_data: dict) -> PsyTest:
    return await psy_tests_repo.create_psy_test(psy_test_data)


async def update_psy_test(psy_test_id: UUID, psy_test_data: dict) -> PsyTest | None:
    psy_test_item, previous_image = await psy_tests_repo.update_psy_test_with_previous_image(
        psy_test_id, psy_test_data,
    )
    if psy_test_item is not None and "image" in psy_test_data and previous_image != psy_test_item.image:
        await run_in_threadpool(remove_psy_test_image, psy_test_id, previous_image)
    return psy_test_item


async def upload_psy_test_image(psy_test_id: UUID, image: UploadFile) -> PsyTest | None:
    try:
        if await psy_tests_repo.get_psy_test_by_id(psy_test_id) is None:
            return None
        # Ограничиваем чтение, даже если Content-Length отсутствует или намеренно искажён
        contents = await image.read(MAX_IMAGE_SIZE + 1)
        image_url = await run_in_threadpool(save_psy_test_image, psy_test_id, contents, image.content_type)
    finally:
        await image.close()

    try:
        psy_test_item = await update_psy_test(psy_test_id, {"image": image_url})
    except Exception:
        await run_in_threadpool(remove_psy_test_image, psy_test_id, image_url)
        raise
    if psy_test_item is None:
        # Тест могли удалить во время обработки файла
        await run_in_threadpool(remove_psy_test_image, psy_test_id, image_url)
    return psy_test_item


async def delete_psy_test(psy_test_id: UUID) -> bool:
    deleted, previous_image = await psy_tests_repo.delete_psy_test_with_previous_image(psy_test_id)
    if deleted:
        await run_in_threadpool(remove_psy_test_image, psy_test_id, previous_image)
    return deleted
