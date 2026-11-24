"""APScheduler background jobs.

The scheduler runs inside the FastAPI process for this MVP, so monitoring keeps
running when users close their browsers.
"""

from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="UTC")


def _watch_job() -> None:
    from app.workers.watch_worker import run_watch_checks

    try:
        run_watch_checks()
    except Exception:
        logger.exception("Scheduled watch run failed")


def _brief_job() -> None:
    from app.workers.morning_brief import send_morning_briefs

    try:
        send_morning_briefs(language=settings.brief_language)
    except Exception:
        logger.exception("Scheduled morning brief failed")


def start_scheduler() -> None:
    if scheduler.running:
        return

    scheduler.add_job(
        _watch_job,
        trigger=IntervalTrigger(minutes=settings.watch_interval_minutes),
        id="watch_checks",
        replace_existing=True,
        next_run_time=datetime.now(scheduler.timezone),
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    if settings.morning_brief_enabled:
        scheduler.add_job(
            _brief_job,
            trigger=CronTrigger(hour=settings.morning_brief_hour_utc, minute=0),
            id="morning_brief",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    scheduler.start()
    logger.info(
        "Scheduler started: watch checks every %s minutes", settings.watch_interval_minutes
    )


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def scheduler_status() -> dict:
    jobs = []
    if scheduler.running:
        for job in scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "next_run_at": job.next_run_time.isoformat() if job.next_run_time else None,
                    "trigger": str(job.trigger),
                }
            )
    return {
        "running": scheduler.running,
        "interval_minutes": settings.watch_interval_minutes,
        "jobs": jobs,
    }
