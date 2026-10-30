"""ARQ worker: runs queued scrape jobs and the daily scheduled scrape.

Start with `arq toolkit.worker.scheduler.WorkerSettings` (the `worker` compose service).
"""

import uuid
from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

from toolkit.config import get_settings
from toolkit.db.session import get_sessionmaker
from toolkit.logging import configure_logging, get_logger
from toolkit.services.jobs import create_job, run_scrape_job

log = get_logger(__name__)


def _sink() -> Any:
    from toolkit.integrations.factory import build_change_sink

    return build_change_sink(get_settings())


async def scrape_task(ctx: dict[str, Any], job_id: str) -> str:
    job = await run_scrape_job(uuid.UUID(job_id), get_settings(), get_sessionmaker(), sink=_sink())
    return job.status.value


async def scheduled_scrape(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    for target in settings.schedule_targets:
        async with get_sessionmaker()() as session:
            job = await create_job(session, "scrape", target)
        log.info("scheduled_scrape_queued", target=target, job_id=str(job.id))
        await run_scrape_job(job.id, settings, get_sessionmaker(), sink=_sink())


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    log.info("worker_started", schedule_hour_utc=settings.schedule_hour_utc)


class WorkerSettings:
    functions: ClassVar[list[Any]] = [scrape_task]
    cron_jobs: ClassVar[list[Any]] = [
        cron(scheduled_scrape, hour={get_settings().schedule_hour_utc}, minute={0})
    ]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 2
    job_timeout = 1800
