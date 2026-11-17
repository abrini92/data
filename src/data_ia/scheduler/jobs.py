"""APScheduler wiring for the six agent jobs / offline cycle."""

from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from data_ia.agents.pipeline import run_offline_cycle
from data_ia.config import get_settings

log = logging.getLogger(__name__)


def daily_cycle_job() -> None:
    result = run_offline_cycle(persist=True)
    log.info(
        "offline cycle done db=%s P=%s",
        result.get("db_mode"),
        result.get("final_probability"),
    )


def build_scheduler() -> BlockingScheduler:
    settings = get_settings()
    sched = BlockingScheduler()
    if settings.scheduler_enabled:
        sched.add_job(daily_cycle_job, "cron", hour=6, minute=0, id="daily_cycle")
    return sched


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.scheduler_enabled:
        log.info("SCHEDULER_ENABLED=false — running one cycle then exiting")
        daily_cycle_job()
        return
    sched = build_scheduler()
    log.info("starting scheduler")
    sched.start()


if __name__ == "__main__":
    main()
