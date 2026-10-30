"""HubSpot CRM: upsert contacts by email with a private-app token."""

import csv
from pathlib import Path
from typing import Protocol

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from toolkit.logging import get_logger

log = get_logger(__name__)


class HubSpotClient(Protocol):
    async def upsert_contact(self, email: str, properties: dict[str, str]) -> str:
        """Create or update the contact with this email; return its HubSpot id."""
        ...


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)


class HttpHubSpotClient:
    """Uses the batch upsert endpoint with `idProperty=email`, so a repeat call
    updates the same contact instead of failing with 409 Conflict."""

    def __init__(
        self,
        token: str,
        base_url: str = "https://api.hubapi.com",
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
            transport=transport,
        )

    async def upsert_contact(self, email: str, properties: dict[str, str]) -> str:
        body = {
            "inputs": [
                {"id": email, "idProperty": "email", "properties": {"email": email, **properties}}
            ]
        }
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(4),
            wait=wait_random_exponential(multiplier=0.5, max=10),
            retry=retry_if_exception(_retryable),
            reraise=True,
        ):
            with attempt:
                resp = await self._client.post("/crm/v3/objects/contacts/batch/upsert", json=body)
                resp.raise_for_status()
        contact_id = str(resp.json()["results"][0]["id"])
        log.info("hubspot_upserted", contact_id=contact_id)
        return contact_id

    async def aclose(self) -> None:
        await self._client.aclose()


class DemoHubSpotClient:
    """Demo mode: no token configured. Logs and writes what would be sent."""

    def __init__(self, directory: Path) -> None:
        self._path = directory / "hubspot_contacts.csv"

    async def upsert_contact(self, email: str, properties: dict[str, str]) -> str:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        new = not self._path.exists()
        with self._path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if new:
                writer.writerow(["email", *sorted(properties)])
            writer.writerow([email, *(properties[k] for k in sorted(properties))])
        log.info("would_send_hubspot", mode="demo", email=email, file=str(self._path))
        return f"demo-{email}"


class FakeHubSpotClient:
    """In-memory, for tests: upsert semantics keyed by email."""

    def __init__(self) -> None:
        self.contacts: dict[str, dict[str, str]] = {}

    async def upsert_contact(self, email: str, properties: dict[str, str]) -> str:
        self.contacts.setdefault(email, {}).update(properties)
        return f"fake-{list(self.contacts).index(email) + 1}"
