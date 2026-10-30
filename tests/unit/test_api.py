import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from toolkit.api.main import create_app
from toolkit.config import Settings, get_settings
from toolkit.db.session import get_sessionmaker, session_scope
from toolkit.scraping.base import ScrapedItem, ScrapeResult
from toolkit.services.changes import apply_scrape_result
from toolkit.services.jobs import create_job

KEY = {"X-API-Key": "test-key"}


class RecordingDispatcher:
    def __init__(self) -> None:
        self.jobs: list[uuid.UUID] = []

    async def dispatch(self, job_id: uuid.UUID) -> None:
        self.jobs.append(job_id)

    async def close(self) -> None:
        pass


@pytest.fixture
def dispatcher() -> RecordingDispatcher:
    return RecordingDispatcher()


@pytest.fixture
async def client(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings: Settings,
    dispatcher: RecordingDispatcher,
) -> AsyncIterator[httpx.AsyncClient]:
    test_settings = settings.model_copy(
        update={"api_key": SecretStr("test-key"), "lead_score_threshold": 60}
    )
    app = create_app(dispatcher)
    app.state.dispatcher = dispatcher

    async def _session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as s:
            yield s

    app.dependency_overrides[session_scope] = _session
    app.dependency_overrides[get_sessionmaker] = lambda: sessionmaker
    app.dependency_overrides[get_settings] = lambda: test_settings
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _seed(sm: async_sessionmaker[AsyncSession]) -> None:
    async with sm() as s:
        job = await create_job(s, "scrape", "books")
        items = [
            ScrapedItem("books", "a_1", "https://books.toscrape.com/a_1", "A", price=None),
            ScrapedItem("books", "b_2", "https://books.toscrape.com/b_2", "B", in_stock=False),
        ]
        await apply_scrape_result(s, ScrapeResult("books", items=items), job, 0)
        await s.commit()


async def test_health(client: httpx.AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"


async def test_scrape_requires_api_key(client: httpx.AsyncClient) -> None:
    r = await client.post("/jobs/scrape", params={"target": "books"})
    assert r.status_code == 401


async def test_scrape_rejects_unknown_target(client: httpx.AsyncClient) -> None:
    r = await client.post("/jobs/scrape", params={"target": "amazon"}, headers=KEY)
    assert r.status_code == 422


async def test_scrape_enqueues_and_job_is_readable(
    client: httpx.AsyncClient, dispatcher: RecordingDispatcher
) -> None:
    r = await client.post("/jobs/scrape", params={"target": "books"}, headers=KEY)
    assert r.status_code == 202
    job_id = r.json()["id"]
    assert dispatcher.jobs == [uuid.UUID(job_id)]
    r = await client.get(f"/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    assert (await client.get(f"/jobs/{uuid.uuid4()}")).status_code == 404


async def test_products_history_changes_and_csv(
    client: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _seed(sessionmaker)
    products = (await client.get("/products")).json()
    assert {p["external_id"] for p in products} == {"a_1", "b_2"}
    assert len((await client.get("/products", params={"in_stock": False})).json()) == 1

    history = (await client.get(f"/products/{products[0]['id']}/history")).json()
    assert len(history) == 1
    assert (await client.get("/products/999/history")).status_code == 404

    assert (await client.get("/changes")).json() == []  # new_product hidden by default
    new = (await client.get("/changes", params={"include_new": True})).json()
    assert len(new) == 2
    since = (await client.get("/changes", params={"since": "2999-01-01T00:00:00Z"})).json()
    assert since == []

    r = await client.get("/export/products.csv")
    assert r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0].startswith("id,source,external_id")
    assert len(r.text.strip().splitlines()) == 3


LEAD = {
    "email": "Jane@AcmeOutdoor.de",
    "name": "Jane Doe",
    "company": "Acme Outdoor GmbH",
    "website": "https://www.acmeoutdoor.de",
    "budget_usd": 6000,
    "message": "We need a pricing quote for monitoring 500 competitor products every day.",
}


async def test_lead_is_scored_enriched_and_idempotent(client: httpx.AsyncClient) -> None:
    assert (await client.post("/leads", json=LEAD)).status_code == 401

    r = await client.post("/leads", json=LEAD, headers=KEY)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "jane@acmeoutdoor.de"
    assert body["company_domain"] == "acmeoutdoor.de"
    assert body["country"] == "DE"
    assert body["qualified"] is True
    assert body["score"] >= 60
    assert body["duplicate"] is False

    again = await client.post("/leads", json=LEAD, headers=KEY)
    assert again.status_code == 200
    assert again.json()["id"] == body["id"]
    assert again.json()["duplicate"] is True


async def test_low_quality_lead_not_qualified(client: httpx.AsyncClient) -> None:
    r = await client.post("/leads", json={"email": "someone@gmail.com"}, headers=KEY)
    assert r.status_code == 201
    assert r.json()["qualified"] is False
    assert r.json()["company_domain"] is None


async def test_invalid_email_rejected(client: httpx.AsyncClient) -> None:
    r = await client.post("/leads", json={"email": "not-an-email"}, headers=KEY)
    assert r.status_code == 422


async def test_dashboard_endpoints(
    client: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _seed(sessionmaker)
    page = await client.get("/dashboard/")
    assert page.status_code == 200
    assert "Competitor Monitor" in page.text

    stats = (await client.get("/stats")).json()
    assert stats["products_total"] == 2
    assert stats["out_of_stock"] == 1
    assert stats["last_run"] is None  # seeded job never ran

    jobs = (await client.get("/jobs")).json()
    assert len(jobs) == 1 and jobs[0]["status"] == "queued"


async def test_lead_list_requires_key(client: httpx.AsyncClient) -> None:
    assert (await client.get("/leads")).status_code == 401
    await client.post("/leads", json=LEAD, headers=KEY)
    rows = (await client.get("/leads", headers=KEY)).json()
    assert rows[0]["email"] == "jane@acmeoutdoor.de"
