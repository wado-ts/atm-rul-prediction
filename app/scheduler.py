"""
In-process scheduler: fires the prediction pipeline automatically every day
at midnight (server local time), in addition to the manual button in the
UI. Both paths call the exact same app.pipeline.run_pipeline().
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.pipeline import run_pipeline

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _scheduled_run() -> None:
    logger.info("Midnight scheduled prediction run starting")
    await run_pipeline(triggered_by="scheduler")


def start_scheduler() -> None:
    settings = get_settings()
    scheduler.add_job(
        _scheduled_run,
        trigger=CronTrigger(hour=settings.daily_run_hour, minute=settings.daily_run_minute),
        id="daily_rul_prediction",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info(
        "Scheduler started: daily run at %02d:%02d",
        settings.daily_run_hour,
        settings.daily_run_minute,
    )


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
