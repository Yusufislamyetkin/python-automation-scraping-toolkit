"""Business flows on top of the integration clients.

Flow 1 (`AlertingChangeSink`): change events -> Sheet (`changes` + `products` tabs) -> alert.
Flow 2 (`CrmLeadSink`): lead -> Sheet (`leads` tab) -> HubSpot if qualified -> alert.
"""

from collections import Counter

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from toolkit.db.models import ChangeEvent, ChangeType, JobRun, Lead, LeadStatus
from toolkit.db.repositories import all_products
from toolkit.integrations.hubspot import HubSpotClient
from toolkit.integrations.notifier import Notifier
from toolkit.integrations.sheets import SheetsClient
from toolkit.logging import get_logger
from toolkit.services.export import COLUMNS, product_rows

log = get_logger(__name__)

CHANGE_HEADER = ["detected_at", "type", "source", "title", "old", "new", "pct_change", "url"]
LEAD_HEADER = ["created_at", "email", "name", "company", "domain", "country", "score", "status"]
ICONS = {
    ChangeType.PRICE_DROP: "📉",
    ChangeType.PRICE_RISE: "📈",
    ChangeType.BACK_IN_STOCK: "✅",
    ChangeType.OUT_OF_STOCK: "⛔",
}
MAX_ALERT_LINES = 20


def change_row(e: ChangeEvent) -> list[str]:
    return [
        e.created_at.isoformat(timespec="seconds"),
        e.type.value,
        e.product.source,
        e.product.title,
        e.old_value or "",
        e.new_value or "",
        "" if e.pct_change is None else f"{e.pct_change}",
        e.product.url,
    ]


def format_alert(events: list[ChangeEvent]) -> str:
    lines = []
    for e in events[:MAX_ALERT_LINES]:
        pct = f" ({e.pct_change:+}%)" if e.pct_change is not None else ""
        lines.append(
            f"{ICONS.get(e.type, '•')} {e.type.value.replace('_', ' ')}: {e.product.title} "
            f"{e.old_value} -> {e.new_value}{pct} {e.product.url}"
        )
    if len(events) > MAX_ALERT_LINES:
        lines.append(f"...and {len(events) - MAX_ALERT_LINES} more")
    return "\n".join(lines)


async def sync_products_sheet(
    sheets: SheetsClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> int:
    async with sessionmaker() as session:
        products = await all_products(session)
    await sheets.replace_rows("products", COLUMNS, product_rows(products))
    return len(products)


class AlertingChangeSink:
    def __init__(
        self,
        sheets: SheetsClient,
        notifier: Notifier,
        sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._sheets = sheets
        self._notifier = notifier
        self._sessionmaker = sessionmaker

    async def handle(self, job: JobRun, events: list[ChangeEvent]) -> None:
        # New products are recorded but not alerted on: the first run would
        # otherwise send one message per catalogue item.
        alertable = [e for e in events if e.type is not ChangeType.NEW_PRODUCT]
        new_count = len(events) - len(alertable)

        await self._sheets.append_rows("changes", CHANGE_HEADER, [change_row(e) for e in alertable])
        if self._sessionmaker is not None:
            await sync_products_sheet(self._sheets, self._sessionmaker)

        if alertable:
            counts = Counter(e.type.value for e in alertable)
            summary = ", ".join(f"{n} {t}" for t, n in counts.items())
            subject = f"[{job.target}] {summary}"
            await self._notifier.send(subject, format_alert(alertable))
        log.info("changes_dispatched", alerts=len(alertable), new_products=new_count)


class CrmLeadSink:
    def __init__(self, sheets: SheetsClient, hubspot: HubSpotClient, notifier: Notifier) -> None:
        self._sheets = sheets
        self._hubspot = hubspot
        self._notifier = notifier

    async def handle(self, lead: Lead) -> None:
        if lead.status is LeadStatus.QUALIFIED:
            first, _, last = (lead.name or "").partition(" ")
            props = {
                k: v
                for k, v in {
                    "firstname": first,
                    "lastname": last,
                    "company": lead.company or "",
                    "website": lead.company_domain or "",
                    "country": lead.country or "",
                    "lifecyclestage": "lead",
                }.items()
                if v
            }
            lead.hubspot_contact_id = await self._hubspot.upsert_contact(lead.email, props)
            lead.status = LeadStatus.SYNCED
            org = lead.company or lead.company_domain or "-"
            await self._notifier.send(
                f"New qualified lead (score {lead.score})",
                f"{lead.name or '-'} <{lead.email}> from {org} ({lead.country or '?'})\n"
                f"{(lead.message or '')[:300]}",
            )

        await self._sheets.append_rows(
            "leads",
            LEAD_HEADER,
            [
                [
                    lead.created_at.isoformat(timespec="seconds"),
                    lead.email,
                    lead.name or "",
                    lead.company or "",
                    lead.company_domain or "",
                    lead.country or "",
                    str(lead.score),
                    lead.status.value,
                ]
            ],
        )
