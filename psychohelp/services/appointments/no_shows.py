import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError

from psychohelp.config.logging import get_logger
from psychohelp.repositories.appointments import mark_appointment_no_shows


logger = get_logger(__name__)
MOSCOW = ZoneInfo("Europe/Moscow")


async def run_appointment_no_show_job() -> None:
    while True:
        now = datetime.now(MOSCOW)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            await mark_appointment_no_shows(day_start, now)
        except (SQLAlchemyError, OSError):
            logger.exception("Не удалось обновить статус записей с неявкой")
            await asyncio.sleep(60)
        else:
            next_midnight = day_start + timedelta(days=1)
            await asyncio.sleep(max(0, (next_midnight - datetime.now(MOSCOW)).total_seconds()))
