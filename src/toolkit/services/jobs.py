"""Job orchestration. Every run is recorded in `job_runs`."""

import time
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from toolkit.config import Settings
from toolkit.db.base import utcnow
from toolkit.db.models import ChangeEvent, JobRun, JobStatus
from toolkit.logging import get_logger
from toolkit.scraping.base import Scraper
from toolkit.scraping.factory import Target, open_scraper
from toolkit.services.changes import apply_scrape_result

log = get_logger(__name__)

ScraperOpener = Callable[[Target, Settings], AbstractAsyncContextManager[Scraper]]


class ChangeSink(Protocol):
    """Receives change events after they are committed (Sheets, Slack, email...)."""

    async def handle(self, job: JobRun, events: list[ChangeEvent]) -> None: ...


async def create_job(session: AsyncSession, job_type: str, target: str | None) -> JobRun:
    job = JobRun(job_type=job_type, target=target, status=JobStatus.QUEUED, meta={})
    session.add(job)
    await session.commit()
    return job


async def run_scrape_job(
    job_id: uuid.UUID,
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    opener: ScraperOpener = open_scraper,
    sink: ChangeSink | None = None,
) -> JobRun:
    async with sessionmaker() as session:
        job = await session.get(JobRun, job_id)
        if job is None:
            raise LookupError(f"job {job_id} not found")
        target: Target = job.target  # type: ignore[assignment]
        job.status = JobStatus.RUNNING
        job.started_at = utcnow()
        await session.commit()

        started = time.monotonic()
        bound = log.bind(job_id=str(job_id), target=target)
        bound.info("job_started")
        events: list[ChangeEvent] = []
        try:
            async with opener(target, settings) as scraper:
                result = await scraper.scrape()
            outcome = await apply_scrape_result(
                session, result, job, settings.price_change_threshold_pct
            )
            events = outcome.events or []
            job.items_total = len(result.items) + sum(
                1 for f in result.failures if not f.error.startswith("store:")
            )
            job.items_ok = outcome.ok
            job.items_failed = len(result.failures)
            job.meta = {
                "pages_fetched": result.pages_fetched,
                "change_events": len(events),
                "failures": [
                    {"url": f.url, "error": f.error[:300], "snapshot": f.snapshot_path}
                    for f in result.failures[:20]
                ],
            }
            if job.items_ok == 0:
                job.status = JobStatus.FAILED
                job.error = result.failures[0].error if result.failures else "no items scraped"
            elif job.items_failed:
                job.status = JobStatus.PARTIAL
            else:
                job.status = JobStatus.SUCCEEDED
        except Exception as exc:
            await session.rollback()
            events = []
            job.status = JobStatus.FAILED
            job.error = f"{type(exc).__name__}: {exc}"[:2000]
            bound.exception("job_crashed")
        finally:
            job.finished_at = utcnow()
            job.duration_ms = int((time.monotonic() - started) * 1000)
            await session.commit()
            await session.refresh(job)

        bound.info(
            "job_finished",
            status=job.status.value,
            duration_ms=job.duration_ms,
            items_ok=job.items_ok,
            items_failed=job.items_failed,
            change_events=len(events),
        )

        if sink is not None and events:
            try:
                await sink.handle(job, events)
                now = utcnow()
                for event in events:
                    event.notified_at = now
                await session.commit()
            except Exception:
                # Alerts failing must never flip a finished scrape to failed.
                bound.exception("change_sink_failed")
        return job
