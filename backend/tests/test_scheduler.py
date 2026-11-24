from __future__ import annotations

from datetime import datetime, timezone

from app.core.config import settings
from app.workers import scheduler as scheduler_module


def test_watch_job_is_scheduled_immediately_on_startup(monkeypatch):
    class SchedulerStub:
        running = False
        timezone = timezone.utc

        def __init__(self):
            self.jobs = []

        def add_job(self, func, *, trigger, **kwargs):
            self.jobs.append({"func": func, "trigger": trigger, **kwargs})

        def start(self):
            self.running = True

    stub = SchedulerStub()
    monkeypatch.setattr(scheduler_module, "scheduler", stub)
    monkeypatch.setattr(settings, "morning_brief_enabled", False)

    scheduler_module.start_scheduler()

    assert len(stub.jobs) == 1
    assert stub.jobs[0]["id"] == "watch_checks"
    assert stub.jobs[0]["next_run_time"] <= datetime.now(timezone.utc)
