"""Builds the right scraper for a target name and owns its resources."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from toolkit.config import Settings
from toolkit.scraping.base import Scraper
from toolkit.scraping.books import BooksScraper
from toolkit.scraping.http import PoliteHttpClient
from toolkit.scraping.quotes import PlaywrightRenderer, QuotesScraper

Target = Literal["books", "quotes"]
TARGETS: tuple[Target, ...] = ("books", "quotes")


@asynccontextmanager
async def open_scraper(target: Target, settings: Settings) -> AsyncIterator[Scraper]:
    if target == "books":
        async with PoliteHttpClient(settings) as client:
            yield BooksScraper(settings, client)
    elif target == "quotes":
        async with PlaywrightRenderer(settings) as renderer:
            yield QuotesScraper(settings, renderer)
    else:  # pragma: no cover - guarded by Literal / API validation
        raise ValueError(f"unknown target {target!r}")
