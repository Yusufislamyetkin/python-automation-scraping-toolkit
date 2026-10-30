"""Scraper interface and the data it produces.

Every target (static or JS-rendered) implements `Scraper.scrape()` and returns a
`ScrapeResult`. A row that fails to parse becomes a `ScrapeFailure` instead of
raising, so one broken card never stops the whole job.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol


@dataclass(slots=True)
class ScrapedItem:
    source: str
    external_id: str
    url: str
    title: str
    price: Decimal | None = None
    currency: str = "GBP"
    in_stock: bool = True
    stock_count: int | None = None
    category: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScrapeFailure:
    url: str
    error: str
    snapshot_path: str | None = None


@dataclass(slots=True)
class ScrapeResult:
    source: str
    items: list[ScrapedItem] = field(default_factory=list)
    failures: list[ScrapeFailure] = field(default_factory=list)
    pages_fetched: int = 0


class Scraper(Protocol):
    """One interface for every target, whatever the fetch technology."""

    name: str

    async def scrape(self) -> ScrapeResult: ...


class ParseError(ValueError):
    """Raised by parsers when the expected markup is missing."""
