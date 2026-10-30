"""books.toscrape.com: static HTML, fetched with httpx and parsed with selectolax."""

import asyncio
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser as HTMLParser
from selectolax.lexbor import LexborNode as Node

from toolkit.config import Settings
from toolkit.logging import get_logger
from toolkit.scraping.base import ParseError, ScrapedItem, ScrapeFailure, ScrapeResult
from toolkit.scraping.http import PoliteHttpClient
from toolkit.scraping.snapshots import save_snapshot

log = get_logger(__name__)

SOURCE = "books"
START_URL = "https://books.toscrape.com/catalogue/page-1.html"
_RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
_STOCK_RE = re.compile(r"\((\d+) available\)")


def parse_price(text: str) -> Decimal:
    cleaned = re.sub(r"[^\d.]", "", text)
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ParseError(f"bad price: {text!r}") from exc


def _external_id(href: str) -> str:
    # ".../a-light-in-the-attic_1000/index.html" -> "a-light-in-the-attic_1000"
    parts = [p for p in href.split("/") if p and p != "index.html"]
    if not parts:
        raise ParseError(f"bad product href: {href!r}")
    return parts[-1]


def parse_card(card: Node, page_url: str) -> ScrapedItem:
    link = card.css_first("h3 a")
    price = card.css_first("p.price_color")
    if link is None or price is None:
        raise ParseError("product card missing title link or price")
    href = link.attributes.get("href") or ""
    title = link.attributes.get("title") or link.text(strip=True)
    availability = card.css_first("p.availability")
    in_stock = availability is not None and "in stock" in availability.text().lower()
    rating_node = card.css_first("p.star-rating")
    rating = None
    if rating_node is not None:
        classes = (rating_node.attributes.get("class") or "").split()
        rating = next((_RATINGS[c] for c in classes if c in _RATINGS), None)
    return ScrapedItem(
        source=SOURCE,
        external_id=_external_id(href),
        url=urljoin(page_url, href),
        title=title,
        price=parse_price(price.text()),
        currency="GBP",
        in_stock=in_stock,
        extra={"rating": rating} if rating else {},
    )


def parse_list_page(
    html: str, page_url: str
) -> tuple[list[ScrapedItem], list[ScrapeFailure], str | None]:
    tree = HTMLParser(html)
    cards = tree.css("article.product_pod")
    if not cards:
        raise ParseError("no product cards found on list page")
    items: list[ScrapedItem] = []
    failures: list[ScrapeFailure] = []
    for index, card in enumerate(cards):
        try:
            items.append(parse_card(card, page_url))
        except ParseError as exc:
            failures.append(ScrapeFailure(url=f"{page_url}#card-{index}", error=str(exc)))
    nxt = tree.css_first("li.next a")
    next_url = urljoin(page_url, nxt.attributes["href"] or "") if nxt else None
    return items, failures, next_url


def parse_detail_page(html: str) -> dict[str, object]:
    """Extra fields only the product page has: exact stock count, category, UPC."""
    tree = HTMLParser(html)
    table: dict[str, str] = {}
    for row in tree.css("table.table-striped tr"):
        th, td = row.css_first("th"), row.css_first("td")
        if th is not None and td is not None:
            table[th.text(strip=True)] = td.text(strip=True)
    if "Availability" not in table:
        raise ParseError("product information table missing")
    match = _STOCK_RE.search(table["Availability"])
    crumbs = [a.text(strip=True) for a in tree.css("ul.breadcrumb li a")]
    return {
        "stock_count": int(match.group(1)) if match else 0,
        "in_stock": "in stock" in table["Availability"].lower(),
        "category": crumbs[-1] if len(crumbs) >= 3 else None,
        "upc": table.get("UPC"),
    }


class BooksScraper:
    name = SOURCE

    def __init__(
        self,
        settings: Settings,
        client: PoliteHttpClient,
        *,
        start_url: str = START_URL,
        fetch_details: bool | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._start_url = start_url
        self._fetch_details = (
            settings.books_fetch_details if fetch_details is None else fetch_details
        )

    async def scrape(self) -> ScrapeResult:
        result = ScrapeResult(source=SOURCE)
        url: str | None = self._start_url
        while url and result.pages_fetched < self._settings.max_pages:
            page_url: str = url
            try:
                html = await self._client.get_text(url)
            except Exception as exc:
                log.error("page_fetch_failed", url=url, error=str(exc))
                result.failures.append(ScrapeFailure(url=url, error=f"fetch: {exc}"))
                break
            result.pages_fetched += 1
            try:
                items, failures, url = parse_list_page(html, page_url)
            except ParseError as exc:
                path = save_snapshot(self._settings.snapshot_dir, SOURCE, page_url, html, str(exc))
                result.failures.append(ScrapeFailure(page_url, str(exc), str(path)))
                break
            if failures:
                save_snapshot(
                    self._settings.snapshot_dir,
                    SOURCE,
                    failures[0].url,
                    html,
                    f"{len(failures)} card(s) failed",
                )
            result.items.extend(items)
            result.failures.extend(failures)

        if self._fetch_details:
            await asyncio.gather(*(self._enrich(item, result) for item in result.items))
        log.info(
            "scrape_finished",
            source=SOURCE,
            pages=result.pages_fetched,
            items=len(result.items),
            failures=len(result.failures),
        )
        return result

    async def _enrich(self, item: ScrapedItem, result: ScrapeResult) -> None:
        html = ""
        try:
            html = await self._client.get_text(item.url)
            detail = parse_detail_page(html)
        except Exception as exc:
            path = (
                save_snapshot(self._settings.snapshot_dir, SOURCE, item.url, html, str(exc))
                if html
                else None
            )
            result.failures.append(
                ScrapeFailure(item.url, f"detail: {exc}", str(path) if path else None)
            )
            return
        item.stock_count = detail["stock_count"]  # type: ignore[assignment]
        item.in_stock = bool(detail["in_stock"])
        item.category = detail["category"]  # type: ignore[assignment]
        item.extra["upc"] = detail["upc"]
