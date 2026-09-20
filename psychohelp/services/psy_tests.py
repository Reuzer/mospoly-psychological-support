from uuid import UUID

from psychohelp.models.psy_tests import PsyTest
import psychohelp.repositories.psy_tests as psy_tests_repo


async def get_psy_test_list(skip: int = 0, take: int = 100) -> list[PsyTest]:
    return await psy_tests_repo.get_psy_test_list(skip, take)


async def get_psy_test_by_id(psy_test_id: UUID) -> PsyTest | None:
    return await psy_tests_repo.get_psy_test_by_id(psy_test_id)


async def create_psy_test(psy_test_data: dict) -> PsyTest:
    return await psy_tests_repo.create_psy_test(psy_test_data)


async def update_psy_test(psy_test_id: UUID, psy_test_data: dict) -> PsyTest | None:
    return await psy_tests_repo.update_psy_test(psy_test_id, psy_test_data)


async def delete_psy_test(psy_test_id: UUID) -> bool:
    return await psy_tests_repo.delete_psy_test(psy_test_id)