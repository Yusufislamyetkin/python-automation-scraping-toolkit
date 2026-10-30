"""Change detection: compare a fresh scrape with what we stored last time."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from toolkit.db.base import utcnow
from toolkit.db.models import ChangeEvent, ChangeType, JobRun, PriceSnapshot, Product
from toolkit.logging import get_logger
from toolkit.scraping.base import ScrapedItem, ScrapeFailure, ScrapeResult

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PreviousState:
    price: Decimal | None
    in_stock: bool


@dataclass(frozen=True, slots=True)
class ChangeDraft:
    type: ChangeType
    old_value: str | None
    new_value: str | None
    pct_change: Decimal | None = None


def _fmt(price: Decimal | None) -> str | None:
    return None if price is None else f"{price:.2f}"


def detect_changes(
    previous: PreviousState | None, item: ScrapedItem, threshold_pct: float = 0.0
) -> list[ChangeDraft]:
    """Pure function, easy to unit test. Returns zero or more change drafts."""
    if previous is None:
        return [ChangeDraft(ChangeType.NEW_PRODUCT, None, _fmt(item.price))]

    changes: list[ChangeDraft] = []
    old, new = previous.price, item.price
    if old is not None and new is not None and old != new and old != 0:
        pct = ((new - old) / old * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if abs(pct) >= Decimal(str(threshold_pct)):
            kind = ChangeType.PRICE_DROP if new < old else ChangeType.PRICE_RISE
            changes.append(ChangeDraft(kind, _fmt(old), _fmt(new), pct))

    if not previous.in_stock and item.in_stock:
        changes.append(ChangeDraft(ChangeType.BACK_IN_STOCK, "out", "in"))
    elif previous.in_stock and not item.in_stock:
        changes.append(ChangeDraft(ChangeType.OUT_OF_STOCK, "in", "out"))
    return changes


@dataclass(slots=True)
class ApplyOutcome:
    ok: int = 0
    failed: int = 0
    events: list[ChangeEvent] | None = None


async def apply_scrape_result(
    session: AsyncSession, result: ScrapeResult, job: JobRun, threshold_pct: float
) -> ApplyOutcome:
    """Upsert products, append snapshots, record change events.

    Each item runs in its own SAVEPOINT: a bad row is logged and counted as
    failed, the rest of the batch still commits.
    """
    outcome = ApplyOutcome(events=[])
    assert outcome.events is not None
    keys = [(i.source, i.external_id) for i in result.items]
    existing: dict[tuple[str, str], Product] = {}
    if keys:
        rows = await session.scalars(
            select(Product).where(tuple_(Product.source, Product.external_id).in_(keys))
        )
        existing = {(p.source, p.external_id): p for p in rows}

    now = utcnow()
    for item in result.items:
        try:
            async with session.begin_nested():
                product = existing.get((item.source, item.external_id))
                previous = (
                    PreviousState(product.current_price, product.in_stock) if product else None
                )
                if product is None:
                    product = Product(
                        source=item.source,
                        external_id=item.external_id,
                        first_seen_at=now,
                    )
                    session.add(product)
                    existing[(item.source, item.external_id)] = product
                product.url = item.url
                product.title = item.title[:1024]
                product.category = item.category
                product.currency = item.currency
                product.current_price = item.price
                product.in_stock = item.in_stock
                product.stock_count = item.stock_count
                product.extra = item.extra
                product.last_seen_at = now
                await session.flush()

                session.add(
                    PriceSnapshot(
                        product_id=product.id,
                        job_run_id=job.id,
                        price=item.price,
                        in_stock=item.in_stock,
                        stock_count=item.stock_count,
                        scraped_at=now,
                    )
                )
                for draft in detect_changes(previous, item, threshold_pct):
                    event = ChangeEvent(
                        product_id=product.id,
                        job_run_id=job.id,
                        type=draft.type,
                        old_value=draft.old_value,
                        new_value=draft.new_value,
                        pct_change=draft.pct_change,
                        created_at=now,
                    )
                    event.product = product
                    session.add(event)
                    outcome.events.append(event)
                await session.flush()
            outcome.ok += 1
        except Exception as exc:
            outcome.failed += 1
            log.error("item_store_failed", external_id=item.external_id, error=str(exc))
            result.failures.append(ScrapeFailure(item.url, f"store: {exc}"))
    return outcome
