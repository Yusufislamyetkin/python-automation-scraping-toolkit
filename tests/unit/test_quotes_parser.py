import pytest
import respx

from tests.conftest import fixture_html
from toolkit.config import Settings
from toolkit.scraping.base import ParseError
from toolkit.scraping.quotes import QuotesScraper, parse_quotes_page, quote_id

URL = "https://quotes.toscrape.com/js/"


def test_parse_rendered_page() -> None:
    items, failures, next_url = parse_quotes_page(fixture_html("quotes_js_rendered.html"), URL)
    assert len(items) == 10
    assert failures == []
    assert next_url == "https://quotes.toscrape.com/js/page/2/"
    first = items[0]
    assert first.extra["author"] == "Albert Einstein"
    assert "change" in first.extra["tags"]
    assert first.title.startswith("The world as we have created it")
    assert first.external_id == quote_id(first.title, "Albert Einstein")
    assert first.price is None


def test_raw_html_without_javascript_has_no_quotes() -> None:
    # Proves why this target needs a browser: the server sends an empty shell.
    with pytest.raises(ParseError):
        parse_quotes_page(fixture_html("quotes_js_raw.html"), URL)


class FakeRenderer:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    async def render(self, url: str, wait_for: str) -> str:
        self.calls.append(url)
        return self.pages[url]


@respx.mock
async def test_quotes_scraper_snapshots_unparseable_page(settings: Settings) -> None:
    respx.get("https://quotes.toscrape.com/robots.txt").respond(404)
    renderer = FakeRenderer(
        {
            URL: fixture_html("quotes_js_rendered.html"),
            "https://quotes.toscrape.com/js/page/2/": "<html><body>blocked</body></html>",
        }
    )
    result = await QuotesScraper(settings, renderer).scrape()
    assert len(result.items) == 10
    assert result.pages_fetched == 2
    assert result.failures[0].snapshot_path is not None
