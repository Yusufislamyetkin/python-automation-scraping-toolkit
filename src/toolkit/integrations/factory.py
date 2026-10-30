"""Wires integration clients from settings (filled in with real clients later)."""

from toolkit.config import Settings
from toolkit.db.models import ChangeEvent, JobRun, Lead
from toolkit.logging import get_logger

log = get_logger(__name__)


class LogOnlySink:
    async def handle(self, job: JobRun, events: list[ChangeEvent]) -> None:
        log.info("would_notify", job_id=str(job.id), events=len(events))


def build_change_sink(settings: Settings) -> LogOnlySink:
    return LogOnlySink()


class LogOnlyLeadSink:
    async def handle(self, lead: Lead) -> None:
        log.info("would_sync_lead", lead_id=lead.id, score=lead.score)


def build_lead_sink(settings: Settings) -> LogOnlyLeadSink:
    return LogOnlyLeadSink()
