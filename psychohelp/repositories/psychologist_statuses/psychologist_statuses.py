from datetime import datetime
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from psychohelp.config.config import get_async_db
from psychohelp.models.psychologists import Psychologist
from psychohelp.models.psychologist_statuses import PsychologistStatus, PsychologistStatusType
from psychohelp.repositories.psychologist_statuses.exceptions import (
    OverlappingStatusException,
    InvalidStatusPeriodException,
)
from psychohelp.repositories.psychologists.exceptions import PsychologistNotFoundException

async def set_psychologist_status(psychologist_id: UUID, start_date: datetime, end_date: datetime, status: PsychologistStatusType) -> PsychologistStatus:
    """
    Устанавливает статус психолога на указанный период.
    
    Args:
        psychologist_id: UUID психолога
        start_date: Дата и время начала статуса
        end_date: Дата и время окончания статуса
        status: Тип статуса (vacation, sick)

    Returns:
        PsychologistStatus: Установленный статус психолога
    """
    if start_date >= end_date:
        raise InvalidStatusPeriodException(psychologist_id)
    
    async with get_async_db() as session:
        async with session.begin():
            result = await session.execute(
                select(Psychologist)
                .options(selectinload(Psychologist.statuses))
                .where(Psychologist.user_id == psychologist_id)
            )

            psychologist = result.scalar_one_or_none()
            if not psychologist:
                raise PsychologistNotFoundException(psychologist_id)
            
            for existing_status in psychologist.statuses:
                if not (end_date <= existing_status.start_date or start_date >= existing_status.end_date):
                    raise OverlappingStatusException(psychologist_id)
            
            new_status = PsychologistStatus(
                pid=psychologist_id,
                start_date=start_date,
                end_date=end_date,
                status=status
            )
            session.add(new_status)
            await session.flush()
            return new_status

async def delete_status_by_id(status_id: UUID) -> bool:
    """
    Удаляет статус психолога по его user_id психолога и ID статуса.
    
    Args:
        status_id: UUID статуса психолога
        psychologist_id: UUID психолога
    Returns:
        bool: True, если статус был успешно удален, иначе False
    """
    async with get_async_db() as session:
        async with session.begin():
            result = await session.execute(
                select(PsychologistStatus)
                .where(PsychologistStatus.id == status_id)
            )
            status = result.scalar_one_or_none()

            if not status:
                return False

            await session.delete(status)
            await session.commit()

            return True

async def get_psychologist_statuses_by_id(psychologist_id: UUID) -> list[PsychologistStatus]:
    """
    Получает все статусы психолога по его ID.
    
    Args:
        psychologist_id: UUID психолога
        
    Returns:
        list[PsychologistStatus]: Список статусов психолога
    """
    async with get_async_db() as session:
        result = await session.execute(
            select(PsychologistStatus)
            .where(PsychologistStatus.pid == psychologist_id)
        )
        statuses = result.scalars().all()
        return list(statuses)