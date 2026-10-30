from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from toolkit.config import Settings
from toolkit.db.models import ChangeEvent, ChangeType, JobRun, JobStatus, PriceSnapshot, Product
from toolkit.scraping.base import ScrapedItem, ScrapeFailure, Scraper, ScrapeResult
from toolkit.services.changes import PreviousState, detect_changes
from toolkit.services.jobs import create_job, run_scrape_job


def item(price: str | None = "10.00", in_stock: bool = True, ext: str = "b1") -> ScrapedItem:
    return ScrapedItem(
        source="books",
        external_id=ext,
        url=f"https://books.toscrape.com/{ext}",
        title=f"Book {ext}",
        price=Decimal(price) if price else None,
        in_stock=in_stock,
    )


def test_new_product() -> None:
    [change] = detect_changes(None, item())
    assert change.type is ChangeType.NEW_PRODUCT


def test_price_drop_and_rise_with_pct() -> None:
    [drop] = detect_changes(PreviousState(Decimal("20.00"), True), item("15.00"))
    assert drop.type is ChangeType.PRICE_DROP
    assert drop.pct_change == Decimal("-25.00")
    assert (drop.old_value, drop.new_value) == ("20.00", "15.00")
    [rise] = detect_changes(PreviousState(Decimal("10.00"), True), item("11.00"))
    assert rise.type is ChangeType.PRICE_RISE


def test_threshold_suppresses_small_moves() -> None:
    assert detect_changes(PreviousState(Decimal("100"), True), item("99.50"), 1.0) == []


def test_stock_transitions() -> None:
    [back] = detect_changes(PreviousState(Decimal("10.00"), False), item(in_stock=True))
    assert back.type is ChangeType.BACK_IN_STOCK
    [out] = detect_changes(PreviousState(Decimal("10.00"), True), item(in_stock=False))
    assert out.type is ChangeType.OUT_OF_STOCK


def test_no_change() -> None:
    assert detect_changes(PreviousState(Decimal("10.00"), True), item()) == []


class StaticScraper:
    name = "books"

    def __init__(self, result: ScrapeResult) -> None:
        self.result = result

    async def scrape(self) -> ScrapeResult:
        return self.result


def opener_for(*results: ScrapeResult):  # type: ignore[no-untyped-def]
    queue = list(results)

    @asynccontextmanager
    async def _open(target: str, settings: Settings) -> AsyncIterator[Scraper]:
        yield StaticScraper(queue.pop(0))

    return _open


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[ChangeEvent] = []

    async def handle(self, job: JobRun, events: list[ChangeEvent]) -> None:
        self.events.extend(events)


async def _run(sm: async_sessionmaker[AsyncSession], settings: Settings, opener, sink=None):  # type: ignore[no-untyped-def]
    async with sm() as s:
        job = await create_job(s, "scrape", "books")
    return await run_scrape_job(job.id, settings, sm, opener=opener, sink=sink)


async def test_two_runs_record_history_and_changes(
    sessionmaker: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    first = ScrapeResult("books", items=[item("10.00", ext="a"), item("5.00", ext="b")])
    second = ScrapeResult(
        "books",
        items=[item("8.00", ext="a"), item("5.00", in_stock=False, ext="b")],
        failures=[ScrapeFailure("https://books.toscrape.com/x", "missing price")],
    )
    opener = opener_for(first, second)
    sink = RecordingSink()

    job1 = await _run(sessionmaker, settings, opener)
    assert job1.status is JobStatus.SUCCEEDED
    assert job1.items_ok == 2

    job2 = await _run(sessionmaker, settings, opener, sink)
    assert job2.status is JobStatus.PARTIAL
    assert job2.items_failed == 1
    assert job2.duration_ms is not None
    assert {e.type for e in sink.events} == {ChangeType.PRICE_DROP, ChangeType.OUT_OF_STOCK}

    async with sessionmaker() as s:
        assert await s.scalar(select(func.count()).select_from(PriceSnapshot)) == 4
        assert await s.scalar(select(func.count()).select_from(Product)) == 2
        notified = await s.scalars(select(ChangeEvent).where(ChangeEvent.notified_at.is_not(None)))
        assert len(notified.all()) == 2


async def test_scraper_crash_marks_job_failed(
    sessionmaker: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    @asynccontextmanager
    async def broken(target: str, s: Settings) -> AsyncIterator[Scraper]:
        raise RuntimeError("browser died")
        yield  # pragma: no cover

    job = await _run(sessionmaker, settings, broken)
    assert job.status is JobStatus.FAILED
    assert "browser died" in (job.error or "")
    assert job.finished_at is not None
