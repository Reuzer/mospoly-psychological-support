import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from contextlib import asynccontextmanager

load_dotenv()


class Config:
    POSTGRES_USER = os.getenv("POSTGRES_USER", "myuser")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "mypassword")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "mydatabase")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    # Раньше был захардкожен порт 5432, сейчас берется из env
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    
    DATABASE_URL = (
        f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )

    SECRET_KEY = os.getenv("SECRET_KEY", "secret-key")
    ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    REFRESH_TOKEN_EXPIRE = int(os.getenv("REFRESH_TOKEN_EXPIRE", "43200"))

    APP_PORT = int(os.getenv("APP_PORT", "8000"))
    APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
    RESET_DB_ON_START = os.getenv("RESET_DB_ON_START", "false").lower() == "true"
    RESET_COOKIE_ON_START = os.getenv("RESET_COOKIE_ON_START", "true").lower() == "true"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")

    MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "Психологическая поддержка Мосполитеха")
    MAIL_REQUEST_TIMEOUT_SECONDS = float(os.getenv("MAIL_REQUEST_TIMEOUT_SECONDS", "10"))

    MAIL_SERVICE_URL = os.getenv("MAIL_SERVICE_URL", "https://mail.liquve.space")
    MAIL_SERVICE_FROM_USER = os.getenv("MAIL_SERVICE_FROM_USER", "root")

    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = int(
        os.getenv("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", "60")
    )
    PASSWORD_RESET_URL_TEMPLATE = os.getenv(
        "PASSWORD_RESET_URL_TEMPLATE",
        "http://localhost:3000/reset-password?token={token}",
    )

config = Config()

@asynccontextmanager
async def get_async_db():
    from sqlalchemy import exc

    session: AsyncSession = async_session()
    try:
        yield session
    except exc.SQLAlchemyError:
        await session.rollback()
        raise
    finally:
        await session.close()


async_engine = create_async_engine(config.DATABASE_URL, future=True, echo=True)
async_session = sessionmaker(
    bind=async_engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()
