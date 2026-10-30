"""Wires integration clients from settings (filled in with real clients later)."""

from toolkit.config import Settings
from toolkit.db.models import ChangeEvent, JobRun
from toolkit.logging import get_logger

log = get_logger(__name__)


class LogOnlySink:
    async def handle(self, job: JobRun, events: list[ChangeEvent]) -> None:
        log.info("would_notify", job_id=str(job.id), events=len(events))


def build_change_sink(settings: Settings) -> LogOnlySink:
    return LogOnlySink()
