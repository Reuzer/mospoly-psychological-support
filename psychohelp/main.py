import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import AsyncEngine

from psychohelp.config.config import (
    Base,
    config,
)
from psychohelp.config.logging import setup_logging, get_logger
from psychohelp.routes import api_router
from psychohelp.routes.controllers.users import limiter

from psychohelp.models import (
    users,
    psychologists,
    appointments,
    reviews,
    roles,
    permissions,
    applications,
    articles,
    password_reset_tokens,
    appointment_reschedule_requests,
)

import uvicorn

from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from fastapi.staticfiles import StaticFiles

log_level = os.getenv("LOG_LEVEL", "DEBUG")
log_file_path = os.getenv("LOG_FILE")

setup_logging(
    level=log_level,
    log_file=Path(log_file_path) if log_file_path else None,
)

logger = get_logger(__name__)


async def reset_database(engine: AsyncEngine) -> None:
    logger.warning("Resetting database - dropping all tables")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database reset completed")


engine = create_async_engine(config.DATABASE_URL, echo=False)


def get_application() -> FastAPI:
    application = FastAPI(
        title="Психологическая Служба API",
        description="API для сервиса психологической помощи",
        version="1.0.0",
    )
    application.include_router(api_router)
    config.AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    application.mount(
        "/media/avatars", StaticFiles(directory=config.AVATAR_DIR), name="avatar"
    )

    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost",
            "http://185.128.105.126:8000",
            "http://185.128.105.126:3000",
            "https://185.128.105.126:8000",
            "https://185.128.105.126:3000",
            "http://194.34.239.126",
            "https://194.34.239.126",
            "http://95.31.169.106",
            "https://95.31.169.106",
            "http://95.31.169.106:3000",
            "https://95.31.169.106:3000",
            "http://95.31.169.106:8000",
            "https://95.31.169.106:8000",
            "https://psychohelp-mospoly.ru",
            "https://www.psychohelp-mospoly.ru",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.on_event("startup")
    async def on_startup() -> None:
        logger.info("Starting application")

        if config.RESET_DB_ON_START:
            await reset_database(engine)
        logger.info("Application started successfully")

    @application.on_event("shutdown")
    async def on_shutdown() -> None:
        logger.info("Shutting down application")

    return application


app = get_application()

def main():
    uvicorn.run(
        "psychohelp.main:app",
        host=config.APP_HOST,
        port=config.APP_PORT,
        reload=True,
        log_config=None,
        log_level=log_level.lower(),
    )


if __name__ == "__main__":
    main()
