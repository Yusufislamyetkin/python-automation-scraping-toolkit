"""End-to-end against a real PostgreSQL (Testcontainers): Alembic migrations,
JSONB, enums-as-check, SAVEPOINT per row, and the leads unique constraint."""

from collections.abc import AsyncIterator, Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from toolkit.db.models import ChangeEvent, ChangeType, Lead, PriceSnapshot
from toolkit.scraping.base import ScrapedItem, ScrapeResult
from toolkit.services.changes import apply_scrape_result
from toolkit.services.jobs import create_job
from toolkit.services.leads import LeadIn, ingest_lead

pytestmark = pytest.mark.integration

ROOT = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def pg_url() -> Iterator[str]:
    try:
        try:
            from testcontainers.community.postgres import PostgresContainer
        except ImportError:
            from testcontainers.postgres import PostgresContainer

        container = PostgresContainer("postgres:16-alpine", driver="asyncpg")
        container.start()
    except Exception as exc:  # Docker not available on this machine/runner
        pytest.skip(f"Docker unavailable: {exc}")
    try:
        url = container.get_connection_url()
        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "migrations"))
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        yield url
    finally:
        container.stop()


@pytest.fixture
async def pg_sessionmaker(pg_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(pg_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _item(ext: str, price: str, title: str = "Book") -> ScrapedItem:
    return ScrapedItem(
        "books",
        ext,
        f"https://books.toscrape.com/{ext}",
        title,
        price=Decimal(price),
        extra={"rating": 3},
    )


async def test_scrape_history_and_bad_row_isolation(
    pg_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_sessionmaker() as s:
        job1 = await create_job(s, "scrape", "books")
        await apply_scrape_result(
            s, ScrapeResult("books", items=[_item("a", "10.00"), _item("b", "20.00")]), job1, 0
        )
        await s.commit()

        job2 = await create_job(s, "scrape", "books")
        # A price that overflows NUMERIC(12,2) makes Postgres reject just that row.
        bad = _item("c", "12345678901234.00")
        outcome = await apply_scrape_result(
            s,
            ScrapeResult("books", items=[_item("a", "7.50"), bad, _item("b", "20.00")]),
            job2,
            0,
        )
        await s.commit()

    assert outcome.ok == 2
    assert outcome.failed == 1
    async with pg_sessionmaker() as s:
        assert await s.scalar(select(func.count()).select_from(PriceSnapshot)) == 4
        drops = (
            await s.scalars(select(ChangeEvent).where(ChangeEvent.type == ChangeType.PRICE_DROP))
        ).all()
        assert len(drops) == 1
        assert drops[0].pct_change == Decimal("-25.00")


async def test_lead_unique_constraint_makes_intake_idempotent(
    pg_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    payload = LeadIn(email="ops@shop.nl", company="Shop BV", message="pricing for 200 SKUs")
    async with pg_sessionmaker() as s:
        first = await ingest_lead(s, payload, threshold=60)
    async with pg_sessionmaker() as s:
        second = await ingest_lead(s, payload, threshold=60)
    assert first.duplicate is False
    assert second.duplicate is True
    assert second.lead.id == first.lead.id
    async with pg_sessionmaker() as s:
        assert await s.scalar(select(func.count()).select_from(Lead)) == 1
        lead = await s.scalar(select(Lead))
        assert lead is not None
        assert lead.country == "NL"
        assert "score_reasons" in lead.raw
