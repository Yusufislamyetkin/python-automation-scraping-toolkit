"""How `POST /jobs/scrape` hands a job to a worker: ARQ queue, or in-process fallback."""

import asyncio
import uuid
from typing import Protocol

from toolkit.config import Settings
from toolkit.db.session import get_sessionmaker
from toolkit.logging import get_logger

log = get_logger(__name__)


class JobDispatcher(Protocol):
    async def dispatch(self, job_id: uuid.UUID) -> None: ...

    async def close(self) -> None: ...


class ArqDispatcher:
    def __init__(self, pool: object) -> None:
        self._pool = pool

    async def dispatch(self, job_id: uuid.UUID) -> None:
        await self._pool.enqueue_job("scrape_task", str(job_id))  # type: ignore[attr-defined]

    async def close(self) -> None:
        await self._pool.aclose()  # type: ignore[attr-defined]


class InProcessDispatcher:
    """Used when Redis is unreachable (e.g. `uvicorn` without compose)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tasks: set[asyncio.Task[object]] = set()

    async def dispatch(self, job_id: uuid.UUID) -> None:
        from toolkit.integrations.factory import build_change_sink
        from toolkit.services.jobs import run_scrape_job

        task = asyncio.create_task(
            run_scrape_job(
                job_id,
                self._settings,
                get_sessionmaker(),
                sink=build_change_sink(self._settings),
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()


async def build_dispatcher(settings: Settings) -> JobDispatcher:
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await asyncio.wait_for(
            create_pool(RedisSettings.from_dsn(settings.redis_url)), timeout=3
        )
        log.info("dispatcher", kind="arq")
        return ArqDispatcher(pool)
    except Exception as exc:
        log.warning("dispatcher_fallback_in_process", error=str(exc))
        return InProcessDispatcher(settings)
