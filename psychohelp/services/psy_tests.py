from uuid import UUID

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from psychohelp.models.psy_tests import PsyTest, PsyTestQuestion
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


async def replace_medical_test_questions(test_id: UUID, questions: list[dict]) -> list[PsyTestQuestion]:
    saved, previous_images = await psy_tests_repo.replace_medical_test_questions(test_id, questions)
    for question_id, image in previous_images:
        await run_in_threadpool(remove_psy_test_image, question_id, image)
    return saved


async def update_medical_test_question_image(
    test_id: UUID, question_id: UUID, image_url: str | None,
) -> PsyTestQuestion:
    question, previous_image = await psy_tests_repo.update_medical_test_question_image(
        test_id, question_id, image_url,
    )
    if previous_image != image_url:
        await run_in_threadpool(remove_psy_test_image, question_id, previous_image)
    return question


async def upload_medical_test_question_image(
    test_id: UUID, question_id: UUID, image: UploadFile,
) -> PsyTestQuestion:
    try:
        contents = await image.read(MAX_IMAGE_SIZE + 1)
        image_url = await run_in_threadpool(save_psy_test_image, question_id, contents, image.content_type)
    finally:
        await image.close()

    try:
        return await update_medical_test_question_image(test_id, question_id, image_url)
    except Exception:
        await run_in_threadpool(remove_psy_test_image, question_id, image_url)
        raise
