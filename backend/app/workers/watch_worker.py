from __future__ import annotations

import asyncio
import logging

from app.core.database import SessionLocal
from app.services.monitoring_service import run_due_watches

logger = logging.getLogger(__name__)


def run_watch_checks(limit: int | None = None) -> dict:
    """Open a session and check every due watch. Safe to call from APScheduler."""

    return asyncio.run(_run_watch_checks_async(limit))


async def _run_watch_checks_async(limit: int | None = None) -> dict:
    db = SessionLocal()
    try:
        result = await run_due_watches(db, limit=limit)
        logger.info(
            "Watch run complete: %s checked, %s alert(s) created",
            result["checked"],
            result["alerts_created"],
        )
        return result
    finally:
        db.close()
