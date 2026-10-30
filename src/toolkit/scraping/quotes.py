"""quotes.toscrape.com/js: content is injected by JavaScript, so it is rendered
with headless Chromium (Playwright) before parsing with selectolax.

The site has no prices; each quote is stored as a "product" with author/tags in
`extra`, which is enough to show JS-rendered scraping and new-item detection.
"""

import hashlib
from types import TracebackType
from typing import Protocol, Self
from urllib.parse import urljoin

import httpx
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from toolkit.config import Settings
from toolkit.logging import get_logger
from toolkit.scraping.base import ParseError, ScrapedItem, ScrapeFailure, ScrapeResult
from toolkit.scraping.politeness import RateLimiter, RobotsGuard
from toolkit.scraping.snapshots import save_snapshot

log = get_logger(__name__)

SOURCE = "quotes"
START_URL = "https://quotes.toscrape.com/js/"


class PageRenderer(Protocol):
    """Returns fully rendered HTML for a URL. Playwright in prod, a fake in tests."""

    async def render(self, url: str, wait_for: str) -> str: ...


class PlaywrightRenderer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pw: object | None = None
        self._browser: object | None = None
        self._context: object | None = None

    async def __aenter__(self) -> Self:
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        proxy = {"server": self._settings.proxy_url} if self._settings.proxy_url else None
        browser = await pw.chromium.launch(headless=True, proxy=proxy)  # type: ignore[arg-type]
        context = await browser.new_context(user_agent=self._settings.user_agent)
        self._pw, self._browser, self._context = pw, browser, context
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._browser is not None:
            await self._browser.close()  # type: ignore[attr-defined]
        if self._pw is not None:
            await self._pw.stop()  # type: ignore[attr-defined]

    async def render(self, url: str, wait_for: str) -> str:
        assert self._context is not None, "use PlaywrightRenderer as an async context manager"
        page = await self._context.new_page()  # type: ignore[attr-defined]
        try:
            timeout_ms = self._settings.http_timeout_seconds * 1000
            await page.goto(url, timeout=timeout_ms)
            await page.wait_for_selector(wait_for, timeout=timeout_ms)
            return str(await page.content())
        finally:
            await page.close()


def quote_id(text: str, author: str) -> str:
    return hashlib.sha1(f"{author}|{text}".encode()).hexdigest()[:16]


def parse_quotes_page(
    html: str, page_url: str
) -> tuple[list[ScrapedItem], list[ScrapeFailure], str | None]:
    tree = HTMLParser(html)
    blocks = tree.css("div.quote")
    if not blocks:
        raise ParseError("no rendered quotes found (did JavaScript run?)")
    items: list[ScrapedItem] = []
    failures: list[ScrapeFailure] = []
    for index, block in enumerate(blocks):
        text_node = block.css_first("span.text")
        author_node = block.css_first("small.author")
        if text_node is None or author_node is None:
            failures.append(ScrapeFailure(f"{page_url}#quote-{index}", "missing text or author"))
            continue
        text = text_node.text(strip=True).strip('“”"')
        author = author_node.text(strip=True)
        tags = [t.text(strip=True) for t in block.css("a.tag")]
        items.append(
            ScrapedItem(
                source=SOURCE,
                external_id=quote_id(text, author),
                url=page_url,
                title=text,
                price=None,
                currency="",
                in_stock=True,
                category=author,
                extra={"author": author, "tags": tags},
            )
        )
    nxt = tree.css_first("li.next a")
    next_url = urljoin(page_url, nxt.attributes["href"] or "") if nxt else None
    return items, failures, next_url


class QuotesScraper:
    name = SOURCE

    def __init__(
        self,
        settings: Settings,
        renderer: PageRenderer,
        *,
        start_url: str = START_URL,
        robots_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._renderer = renderer
        self._start_url = start_url
        self._rate = RateLimiter(settings.request_delay_seconds)
        self._robots = RobotsGuard(settings.user_agent, settings.respect_robots_txt)
        self._robots_client = robots_client

    async def scrape(self) -> ScrapeResult:
        result = ScrapeResult(source=SOURCE)
        client = self._robots_client or httpx.AsyncClient(
            headers={"User-Agent": self._settings.user_agent},
            timeout=self._settings.http_timeout_seconds,
            proxy=self._settings.proxy_url,
        )
        try:
            url: str | None = self._start_url
            while url and result.pages_fetched < self._settings.max_pages:
                page_url: str = url
                if not await self._robots.allowed(client, url):
                    result.failures.append(ScrapeFailure(url, "disallowed by robots.txt"))
                    break
                await self._rate.wait()
                try:
                    html = await self._renderer.render(url, "div.quote")
                except Exception as exc:
                    log.error("render_failed", url=url, error=str(exc))
                    result.failures.append(ScrapeFailure(url, f"render: {exc}"))
                    break
                result.pages_fetched += 1
                try:
                    items, failures, url = parse_quotes_page(html, page_url)
                except ParseError as exc:
                    path = save_snapshot(
                        self._settings.snapshot_dir, SOURCE, page_url, html, str(exc)
                    )
                    result.failures.append(ScrapeFailure(page_url, str(exc), str(path)))
                    break
                result.items.extend(items)
                result.failures.extend(failures)
        finally:
            if self._robots_client is None:
                await client.aclose()
        log.info(
            "scrape_finished",
            source=SOURCE,
            pages=result.pages_fetched,
            items=len(result.items),
            failures=len(result.failures),
        )
        return result
