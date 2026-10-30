"""Politeness primitives shared by HTTP and browser scrapers."""

import asyncio
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from toolkit.logging import get_logger

log = get_logger(__name__)


class RateLimiter:
    """Guarantees at least `min_interval` seconds between request starts."""

    def __init__(self, min_interval: float) -> None:
        self._min_interval = min_interval
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def wait(self) -> None:
        async with self._lock:
            delay = self._last + self._min_interval - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = time.monotonic()


class RobotsGuard:
    """Caches robots.txt per host. A missing robots.txt (4xx) means allow-all."""

    def __init__(self, user_agent: str, enabled: bool = True) -> None:
        self._user_agent = user_agent
        self._enabled = enabled
        self._parsers: dict[str, RobotFileParser] = {}

    async def allowed(self, client: httpx.AsyncClient, url: str) -> bool:
        if not self._enabled:
            return True
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        parser = self._parsers.get(origin)
        if parser is None:
            parser = RobotFileParser()
            try:
                resp = await client.get(f"{origin}/robots.txt")
                if resp.status_code >= 400:
                    parser.parse([])
                else:
                    parser.parse(resp.text.splitlines())
            except httpx.HTTPError as exc:
                # Unreachable robots.txt: be conservative and allow, but say so.
                log.warning("robots_unreachable", origin=origin, error=str(exc))
                parser.parse([])
            self._parsers[origin] = parser
        return parser.can_fetch(self._user_agent, url)
