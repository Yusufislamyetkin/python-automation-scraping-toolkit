import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from toolkit.config import Settings
from toolkit.db.base import utcnow
from toolkit.db.models import ChangeEvent, ChangeType, JobRun, Lead, LeadStatus, Product
from toolkit.integrations.factory import build_hubspot, build_sheets, integration_modes
from toolkit.integrations.hubspot import (
    DemoHubSpotClient,
    FakeHubSpotClient,
    HttpHubSpotClient,
)
from toolkit.integrations.notifier import (
    FakeNotifier,
    FallbackNotifier,
    SlackWebhookNotifier,
    TelegramNotifier,
)
from toolkit.integrations.sheets import CsvSheetsClient, FakeSheetsClient
from toolkit.integrations.sinks import AlertingChangeSink, CrmLeadSink


def _event(kind: ChangeType, title: str = "A Light in the Attic") -> ChangeEvent:
    product = Product(
        id=1,
        source="books",
        external_id="x",
        url="https://books.toscrape.com/x",
        title=title,
    )
    e = ChangeEvent(
        product_id=1,
        type=kind,
        old_value="51.77",
        new_value="44.00",
        pct_change=Decimal("-15.01"),
        created_at=utcnow(),
    )
    e.product = product
    return e


def _lead(status: LeadStatus = LeadStatus.QUALIFIED) -> Lead:
    return Lead(
        id=7,
        email="jane@acme.de",
        name="Jane Doe",
        company="Acme",
        company_domain="acme.de",
        country="DE",
        score=80,
        status=status,
        created_at=utcnow(),
        raw={},
    )


async def test_change_sink_writes_sheet_and_alerts_without_new_products(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    sheets, notifier = FakeSheetsClient(), FakeNotifier()
    sink = AlertingChangeSink(sheets, notifier, sessionmaker)
    events = [
        _event(ChangeType.PRICE_DROP),
        _event(ChangeType.OUT_OF_STOCK),
        _event(ChangeType.NEW_PRODUCT),
    ]
    await sink.handle(JobRun(target="books"), events)

    assert len(sheets.tabs["changes"]) == 1 + 2  # header + 2 alertable rows
    assert sheets.tabs["products"][0][0] == "id"
    [(subject, text)] = notifier.sent
    assert "1 price_drop" in subject and "1 out_of_stock" in subject
    assert "-15.01%" in text
    assert "new_product" not in text


async def test_change_sink_silent_when_only_new_products() -> None:
    notifier = FakeNotifier()
    await AlertingChangeSink(FakeSheetsClient(), notifier).handle(
        JobRun(target="books"), [_event(ChangeType.NEW_PRODUCT)]
    )
    assert notifier.sent == []


async def test_qualified_lead_goes_to_hubspot_sheet_and_alert() -> None:
    sheets, hubspot, notifier = FakeSheetsClient(), FakeHubSpotClient(), FakeNotifier()
    lead = _lead()
    await CrmLeadSink(sheets, hubspot, notifier).handle(lead)
    assert hubspot.contacts["jane@acme.de"]["firstname"] == "Jane"
    assert lead.status is LeadStatus.SYNCED
    assert lead.hubspot_contact_id == "fake-1"
    assert sheets.tabs["leads"][1][1] == "jane@acme.de"
    assert "score 80" in notifier.sent[0][0]


async def test_unqualified_lead_only_logged_to_sheet() -> None:
    sheets, hubspot, notifier = FakeSheetsClient(), FakeHubSpotClient(), FakeNotifier()
    await CrmLeadSink(sheets, hubspot, notifier).handle(_lead(LeadStatus.NEW))
    assert hubspot.contacts == {}
    assert notifier.sent == []
    assert len(sheets.tabs["leads"]) == 2


async def test_fallback_used_only_when_all_primaries_fail() -> None:
    email = FakeNotifier("email")
    ok = FallbackNotifier([FakeNotifier("slack")], email)
    await ok.send("s", "t")
    assert email.sent == []

    broken = FallbackNotifier([FakeNotifier("slack", fail=True)], email)
    await broken.send("s", "t")
    assert email.sent == [("s", "t")]


@respx.mock
async def test_hubspot_upsert_by_email_with_retry() -> None:
    route = respx.post("https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(200, json={"results": [{"id": "1234"}]}),
        ]
    )
    client = HttpHubSpotClient("pat-test")
    contact_id = await client.upsert_contact("jane@acme.de", {"firstname": "Jane"})
    await client.aclose()

    assert contact_id == "1234"
    assert route.call_count == 2
    sent = json.loads(route.calls.last.request.content)
    assert sent["inputs"][0] == {
        "id": "jane@acme.de",
        "idProperty": "email",
        "properties": {"email": "jane@acme.de", "firstname": "Jane"},
    }
    assert route.calls.last.request.headers["Authorization"] == "Bearer pat-test"


@respx.mock
async def test_slack_and_telegram_payloads() -> None:
    slack = respx.post("https://hooks.slack.test/T/B/X").respond(200, text="ok")
    tg = respx.post("https://api.telegram.org/botTOKEN/sendMessage").respond(200, json={"ok": True})
    async with httpx.AsyncClient() as http:
        await SlackWebhookNotifier("https://hooks.slack.test/T/B/X", http).send("Subj", "body")
        await TelegramNotifier("TOKEN", "42", http).send("Subj", "body")
    assert json.loads(slack.calls.last.request.content) == {"text": "*Subj*\nbody"}
    assert json.loads(tg.calls.last.request.content)["chat_id"] == "42"


async def test_demo_mode_writes_csv(settings: Settings, tmp_path: Path) -> None:
    assert integration_modes(settings)["sheets"] == "demo"
    sheets = build_sheets(settings)
    hubspot = build_hubspot(settings)
    assert isinstance(sheets, CsvSheetsClient)
    assert isinstance(hubspot, DemoHubSpotClient)

    await sheets.append_rows("leads", ["email"], [["a@b.com"]])
    await sheets.append_rows("leads", ["email"], [["c@d.com"]])
    await hubspot.upsert_contact("a@b.com", {"company": "B"})
    lines = (settings.demo_output_dir / "sheet_leads.csv").read_text().splitlines()
    assert lines == ["email", "a@b.com", "c@d.com"]
    assert (settings.demo_output_dir / "hubspot_contacts.csv").exists()


@pytest.mark.parametrize("missing", ["google_sheet_id", "google_service_account_file"])
def test_partial_google_config_stays_in_demo(settings: Settings, missing: str) -> None:
    cfg = settings.model_copy(
        update={"google_sheet_id": "abc", "google_service_account_file": Path("sa.json")}
    )
    cfg = cfg.model_copy(update={missing: None})
    assert integration_modes(cfg)["sheets"] == "demo"
