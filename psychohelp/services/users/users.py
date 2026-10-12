from psychohelp.repositories import create_access_token, create_refresh_token, verify_password, hash_password, refresh_access_token
from psychohelp.repositories.users import (
    get_user_by_id as repo_get_user_by_id,
    get_user_by_email as repo_get_user_by_email,
    get_user_by_token as repo_get_user_by_token,
    create_user,
    get_avatar,
    UUID,
)
from psychohelp.models.users import User
from psychohelp.services.users import exceptions, models
from psychohelp.schemas.users import UserUpdateRequest
from psychohelp.repositories.users import update_user, get_user_by_id, set_avatar
from psychohelp.services.users.exceptions import UserNotFound, PermissionDenied, InvalidImageError, ImageProcessingError
from psychohelp.repositories import verify_password, hash_password
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from starlette.status import HTTP_409_CONFLICT
from pathlib import Path
from PIL import Image, UnidentifiedImageError
import io


async def get_user_by_id(user_id: UUID) -> User | None:
    return await repo_get_user_by_id(user_id)


async def get_user_by_email(email: str) -> User | None:
    return await repo_get_user_by_email(email)


async def get_user_by_token(token: str) -> User | None:
    return await repo_get_user_by_token(token)


async def register_user(
    first_name: str,
    last_name: str,
    phone_number: str,
    email: str,
    password: str,
    middle_name: str | None = None,
    social_media: str | None = None,
    study_group: str | None = None,
) -> tuple[User, str]:
    new_user = await create_user(
        first_name,
        last_name,
        phone_number,
        email,
        hash_password(password),
        middle_name,
        social_media,
        study_group,
    )
    return new_user, create_access_token(new_user.id), create_refresh_token(new_user.id)


async def login_user(email: str, password: str) -> models.UserWithToken:
    user = await repo_get_user_by_email(email)
    if user is None:
        raise exceptions.UserNotFound()

    if not verify_password(password, user.password):
        raise exceptions.WrongPassword()

    return models.UserWithToken(
        user=user,
        token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


async def update_profile(
    current_user_id: UUID,
    target_user_id: UUID,
    data: UserUpdateRequest,
    is_admin: bool = False
) -> User:
    """
    Обновление профиля.
    Если current_user_id != target_user_id, то требуется is_admin=True.
    """
    if current_user_id != target_user_id and not is_admin:
        raise PermissionDenied("Вы можете редактировать только свой профиль")

    user = await get_user_by_id(target_user_id)
    if not user:
        raise UserNotFound()

    # Исключаем поля, которые не были переданы (None)
    update_dict = data.model_dump(exclude_unset=True)
    if not update_dict:
        return user  # ничего не меняем

    # Проверка уникальности email (если передан новый email)
    if "email" in update_dict:
        existing = await get_user_by_email(update_dict["email"])
        if existing and existing.id != target_user_id:
            raise HTTPException(
                status_code=HTTP_409_CONFLICT,
                detail="Пользователь с таким email уже существует"
            )

    try:
        updated_user = await update_user(target_user_id, update_dict)
        if updated_user is None:
            raise UserNotFound()
    except IntegrityError as e:
        # Другие возможные ошибки уникальности (phone_number и т.д.)
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail="Данные конфликтуют с существующими записями"
        )

    return updated_user


async def change_password(
    user_id: UUID,
    old_password: str,
    new_password: str
) -> None:
    user = await get_user_by_id(user_id)
    if not user:
        raise UserNotFound()

    if not verify_password(old_password, user.password):
        raise ValueError("Неверный старый пароль")

    await update_user(user_id, {"password": hash_password(new_password)})


async def set_user_avatar(avatar, user):
    ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
    BASE_DIR = Path("/app")
    UPLOAD_DIR = BASE_DIR / "srv" / "images" / "avatars"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    file_name = f"{user.id}.webp"
    file_path = UPLOAD_DIR / file_name

    try:
        contents = await avatar.read()

        image_stream = io.BytesIO(contents)

        with Image.open(image_stream) as img:
            if img.format not in ALLOWED_FORMATS:
                raise InvalidImageError(f"Invalid image format: {img.format}")
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGBA")
            else:
                img = img.convert("RGB")

            img.save(file_path, "WEBP", quality=85)
        await set_avatar(file_name, user)

    except UnidentifiedImageError as e:
        if file_path.exists():
            file_path.unlink()
        raise InvalidImageError("Uploaded file is not a valid image.") from e
    
    except OSError as e:
        if file_path.exists():
            file_path.unlink()
        raise ImageProcessingError("Could not process image due to server error.") from e


async def get_user_avatar(user_id):
    user = await get_avatar(user_id)

    if not user:
        raise UserNotFound(user_id)

    avatar_url = f"/media/avatars/{user.avatar}"
    return avatar_url
