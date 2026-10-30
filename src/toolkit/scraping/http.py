"""Polite async HTTP client: UA, proxy, concurrency cap, rate limit, retries, robots.txt."""

import asyncio
from types import TracebackType
from typing import Self

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from toolkit.config import Settings
from toolkit.logging import get_logger
from toolkit.scraping.politeness import RateLimiter, RobotsGuard

log = get_logger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class RobotsDisallowed(RuntimeError):
    pass


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS
    return isinstance(exc, httpx.TransportError)


class PoliteHttpClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        max_attempts: int = 4,
    ) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            headers={"User-Agent": settings.user_agent, "Accept": "text/html"},
            timeout=settings.http_timeout_seconds,
            follow_redirects=True,
            proxy=settings.proxy_url,
            transport=transport,
        )
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)
        self._rate = RateLimiter(settings.request_delay_seconds)
        self._robots = RobotsGuard(settings.user_agent, settings.respect_robots_txt)
        self._max_attempts = max_attempts

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def get_text(self, url: str) -> str:
        if not await self._robots.allowed(self._client, url):
            raise RobotsDisallowed(url)
        async with self._semaphore:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._max_attempts),
                wait=wait_random_exponential(multiplier=0.5, max=10),
                retry=retry_if_exception(_is_retryable),
                reraise=True,
            ):
                with attempt:
                    await self._rate.wait()
                    resp = await self._client.get(url)
                    if resp.status_code in RETRYABLE_STATUS:
                        log.warning(
                            "http_retry",
                            url=url,
                            status=resp.status_code,
                            attempt=attempt.retry_state.attempt_number,
                        )
                    resp.raise_for_status()
                    return resp.text
        raise AssertionError("unreachable")  # pragma: no cover
