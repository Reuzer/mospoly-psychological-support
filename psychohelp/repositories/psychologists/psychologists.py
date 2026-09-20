from uuid import UUID

from psychohelp.constants.rbac import RoleCode
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from psychohelp.config.config import get_async_db
from psychohelp.models.psychologists import Psychologist
from psychohelp.models.users import User
from psychohelp.models.roles import Role
from psychohelp.repositories.psychologists.exceptions import (
    UserNotFoundForPsychologistException,
    PsychologistRoleNotFoundException,
    PsychologistAlreadyExistsException,
)


async def get_psychologist_by_id(psychologist_id: UUID) -> Psychologist | None:
    async with get_async_db() as session:
        result = await session.execute(
            select(Psychologist)
            .options(selectinload(Psychologist.user))
            .filter(Psychologist.id == psychologist_id)
        )
        psychologist = result.scalar_one_or_none()

    return psychologist


async def get_psychologist_by_user_id(user_id: UUID) -> Psychologist | None:
    async with get_async_db() as session:
        result = await session.execute(
            select(Psychologist)
            .options(selectinload(Psychologist.user))
            .filter(Psychologist.user_id == user_id)
        )
        psychologist = result.scalar_one_or_none()

    return psychologist


async def get_psychologists(skip: int = 0, take: int = 10) -> list[Psychologist]:
    """
    Получить список психологов с пагинацией
    """
    async with get_async_db() as session:
        query = await session.execute(
            select(Psychologist)
            .options(joinedload(Psychologist.user))
            .offset(skip)
            .limit(take)
        )

    result = query.scalars().all()
    return result


async def create_psychologist(user_id: UUID, psychologist_data: dict) -> Psychologist:
    async with get_async_db() as session:
        async with session.begin():
            user_result = await session.execute(
                select(User)
                .options(selectinload(User.roles))
                .where(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if user is None:
                raise UserNotFoundForPsychologistException(user_id)
            
            existing_psychologist_result = await session.execute(
                select(Psychologist).where(Psychologist.user_id == user_id)
            )
            if existing_psychologist_result.scalar_one_or_none() is not None:
                raise PsychologistAlreadyExistsException(user_id)
            
            psychologist = Psychologist(user_id=user_id, **psychologist_data)
            session.add(psychologist)
            
            psychologist_role_result = await session.execute(
                select(Role).where(Role.code == RoleCode.PSYCHOLOGIST.value)
            )
            psychologist_role = psychologist_role_result.scalar_one_or_none()
            
            if not psychologist_role:
                raise PsychologistRoleNotFoundException()
            
            user_role_codes = {role.code for role in user.roles}
            
            if RoleCode.PSYCHOLOGIST.value not in user_role_codes:
                user.roles.append(psychologist_role)
            
            await session.flush()

            result = await session.execute(
                select(Psychologist)
                .options(selectinload(Psychologist.user))
                .where(Psychologist.id == psychologist.id)
            )
            psychologist = result.scalar_one()
            
            await session.commit()
    
    return psychologist


async def delete_psychologist(psychologist_id: UUID) -> bool:
    """
    Удалить запись психолога и убрать роль 'psychologist' у пользователя
    
    Args:
        psychologist_id: UUID психолога
        
    Returns:
        bool: True если удалено, False если не найдено
    """
    async with get_async_db() as session:
        async with session.begin():
            result = await session.execute(
                select(Psychologist)
                .options(selectinload(Psychologist.user).selectinload(User.roles))
                .where(Psychologist.id == psychologist_id)
            )
            psychologist = result.scalar_one_or_none()
            
            if psychologist is None:
                return False
            
            user = psychologist.user
            
            psychologist_role = next(
                (role for role in user.roles if role.code == RoleCode.PSYCHOLOGIST.value),
                None
            )
            if psychologist_role:
                user.roles.remove(psychologist_role)
            
            await session.delete(psychologist)
            await session.commit()
    
    return True

async def check_psychologist_availability(psychologist_id: UUID, scheduled_time) -> bool:
    """
    Проверяет доступность психолога на указанное время.
    
    Args:
        psychologist_id: UUID психолога
        scheduled_time: Время записи (datetime)
        
    Returns:
        bool: True если психолог доступен, False если недоступен
    """
    async with get_async_db() as session:
        result = await session.execute(
            select(Psychologist)
            .options(selectinload(Psychologist.statuses))
            .where(Psychologist.id == psychologist_id)
        )
        psychologist = result.scalar_one_or_none()
        
        if psychologist is None:
            raise PsychologistRoleNotFoundException()
        
        for status in psychologist.statuses:
            if status.start_date <= scheduled_time <= status.end_date:
                return False
        
    return True