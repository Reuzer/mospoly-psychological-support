from uuid import UUID

from psychohelp.models.psychologists import Psychologist
from psychohelp.repositories.psychologists.psychologists import (
    get_psychologist_by_id as repo_get_psychologist_by_id,
    get_psychologist_by_user_id,
    get_psychologists as repo_get_psychologists,
    update_own_psychologist,
    create_psychologist as repo_create_psychologist,
    delete_psychologist as repo_delete_psychologist,
)


async def get_psychologist_by_id(psychologist_id: UUID) -> Psychologist | None:
    """
    Получить психолога по ID
    
    Args:
        psychologist_id: UUID психолога
        
    Returns:
        Psychologist | None: ORM модель психолога или None если не найден
    """
    return await repo_get_psychologist_by_id(psychologist_id)


async def get_psychologists(skip: int = 0, take: int = 10) -> list[Psychologist]:
    """
    Получить список всех психологов с пагинацией
    
    Args:
        skip: Количество записей для пропуска
        take: Количество записей для получения
        
    Returns:
        list[Psychologist]: Список ORM моделей психологов
    """
    psychologists = await repo_get_psychologists(skip=skip, take=take)
    return list(psychologists)


async def create_psychologist(user_id: UUID, psychologist_data: dict) -> Psychologist:
    return await repo_create_psychologist(user_id, psychologist_data)


async def delete_psychologist(psychologist_id: UUID) -> bool:
    return await repo_delete_psychologist(psychologist_id)

