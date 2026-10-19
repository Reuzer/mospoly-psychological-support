from psychohelp.constants.rbac import RoleCode
from psychohelp.models.users import User
from psychohelp.models.roles import Role
from psychohelp.config.config import get_async_db
from psychohelp.repositories import get_user_id_from_token, UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import selectinload
from sqlalchemy import update 
from psychohelp.services.users.exceptions import ImageProcessingError

async def get_user_by_id(user_id: UUID) -> User | None:
    async with get_async_db() as session:
        result = await session.execute(
            select(User)
            .options(selectinload(User.roles))        
            .filter(User.id == user_id)
        )
    return result.scalar_one_or_none()


async def get_user_by_email(email: str) -> User | None:
    async with get_async_db() as session:
        result = await session.execute(
            select(User)
            .options(selectinload(User.roles))         
            .filter(User.email == email)
        )
    return result.scalar_one_or_none()


async def get_user_by_token(token: str) -> User | None:
    id = get_user_id_from_token(token)
    return await get_user_by_id(id)


async def create_user(
    first_name: str,
    last_name: str,
    phone_number: str,
    email: str,
    hashed_password: str,
    middle_name: str | None = None,
    social_media: str | None = None,
    study_group: str | None = None,
) -> User:
    async with get_async_db() as session:
        try:
            existing_user = await session.execute(
                select(User).filter(User.email == email)
            )
            if existing_user.scalar_one_or_none():
                raise ValueError("Пользователь с таким email уже существует")

            new_user = User(
                first_name=first_name,
                middle_name=middle_name,
                last_name=last_name,
                phone_number=phone_number,
                email=email,
                social_media=social_media,
                password=hashed_password,
                study_group=study_group,
            )

            session.add(new_user)
            await session.flush()
            
            user_role_result = await session.execute(
                select(Role).where(Role.code == RoleCode.USER.value)
            )
            user_role = user_role_result.scalar_one_or_none()
            
            if user_role:
                await session.execute(
                    select(User)
                    .options(selectinload(User.roles))
                    .where(User.id == new_user.id)
                )
                new_user.roles.append(user_role)
            
            await session.commit()
            await session.refresh(new_user, ['roles']) 
            return new_user

        except IntegrityError:
            await session.rollback()
            raise

async def update_user(user_id: UUID, update_data: dict) -> User | None:
    """Обновить данные пользователя"""
    async with get_async_db() as session:
        try:
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(**update_data)
            )
            await session.execute(stmt)
            await session.commit()
            
            # Перезагружаем пользователя с отношениями после обновления
            result = await session.execute(
                select(User)
                .options(selectinload(User.roles))
                .filter(User.id == user_id)
            )
            return result.scalar_one_or_none()
        except IntegrityError:
            await session.rollback()
            raise


async def set_avatar(avatar_file_name, user):
    async with get_async_db() as session:
        try:
            user_id = user.id

            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(avatar = avatar_file_name)
            )

            await session.execute(stmt)
            await session.commit()

        except SQLAlchemyError as e:
            await session.rollback()
            raise ImageProcessingError("Could not save avatar info to database.") from e

async def get_avatar(user_id):
    async with get_async_db() as session:
        stmt = (
            select(User.id, User.avatar)
            .where(User.id == user_id)
        )

        result = await session.execute(stmt)
        user = result.one_or_none()

        return user