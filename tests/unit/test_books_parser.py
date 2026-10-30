from decimal import Decimal

import httpx
import pytest
import respx

from tests.conftest import fixture_html
from toolkit.config import Settings
from toolkit.scraping.base import ParseError
from toolkit.scraping.books import (
    BooksScraper,
    parse_detail_page,
    parse_list_page,
    parse_price,
)
from toolkit.scraping.http import PoliteHttpClient

PAGE1 = "https://books.toscrape.com/catalogue/page-1.html"
PAGE2 = "https://books.toscrape.com/catalogue/page-2.html"


def test_parse_list_page_extracts_all_cards() -> None:
    items, failures, next_url = parse_list_page(fixture_html("books_list.html"), PAGE1)
    assert len(items) == 20
    assert failures == []
    assert next_url == PAGE2
    first = items[0]
    assert first.external_id == "a-light-in-the-attic_1000"
    assert first.title == "A Light in the Attic"
    assert first.price == Decimal("51.77")
    assert first.in_stock is True
    assert first.url.endswith("/catalogue/a-light-in-the-attic_1000/index.html")
    assert first.extra["rating"] == 3


def test_broken_card_is_reported_not_raised() -> None:
    html = fixture_html("books_list.html").replace(
        '<p class="price_color">£51.77</p>', "<p>price removed</p>", 1
    )
    items, failures, _ = parse_list_page(html, PAGE1)
    assert len(items) == 19
    assert len(failures) == 1
    assert "price" in failures[0].error


def test_parse_list_page_without_cards_raises() -> None:
    with pytest.raises(ParseError):
        parse_list_page("<html><body>maintenance</body></html>", PAGE1)


def test_parse_detail_page() -> None:
    detail = parse_detail_page(fixture_html("books_detail.html"))
    assert detail["stock_count"] == 22
    assert detail["in_stock"] is True
    assert detail["category"] == "Poetry"
    assert detail["upc"] == "a897fe39b1053632"


@pytest.mark.parametrize(("raw", "expected"), [("£51.77", "51.77"), ("Â£10.00", "10.00")])
def test_parse_price(raw: str, expected: str) -> None:
    assert parse_price(raw) == Decimal(expected)


@respx.mock
async def test_scraper_follows_pagination_and_retries(settings: Settings) -> None:
    respx.get("https://books.toscrape.com/robots.txt").respond(404)
    page1 = respx.get(PAGE1).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, text=fixture_html("books_list.html"))]
    )
    respx.get(PAGE2).respond(200, text="<html><body>layout changed</body></html>")

    async with PoliteHttpClient(settings) as client:
        result = await BooksScraper(settings, client, fetch_details=False).scrape()

    assert page1.call_count == 2  # 503 retried
    assert len(result.items) == 20
    assert result.pages_fetched == 2
    # page 2 failed to parse -> recorded with an HTML snapshot, job not aborted
    assert len(result.failures) == 1
    assert result.failures[0].snapshot_path is not None
    assert list(settings.snapshot_dir.glob("books_*.html"))


@respx.mock
async def test_robots_disallow_is_respected(settings: Settings) -> None:
    respx.get("https://books.toscrape.com/robots.txt").respond(
        200, text="User-agent: *\nDisallow: /catalogue/"
    )
    page = respx.get(PAGE1).respond(200, text=fixture_html("books_list.html"))
    async with PoliteHttpClient(settings) as client:
        result = await BooksScraper(settings, client).scrape()
    assert page.call_count == 0
    assert result.items == []
    assert "fetch" in result.failures[0].error
