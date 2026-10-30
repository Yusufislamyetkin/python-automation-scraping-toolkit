"""Lead intake: validate -> dedupe -> enrich -> score -> store -> hand off to CRM sink.

Scoring is a transparent rule set (no ML) so a sales team can read and tune it.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from toolkit.db.models import Lead, LeadStatus
from toolkit.logging import get_logger

log = get_logger(__name__)

FREE_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "live.com",
        "icloud.com",
        "aol.com",
        "proton.me",
        "protonmail.com",
        "gmx.com",
        "yandex.com",
        "mail.com",
    }
)
TLD_COUNTRY = {
    "uk": "GB",
    "de": "DE",
    "fr": "FR",
    "nl": "NL",
    "tr": "TR",
    "es": "ES",
    "it": "IT",
    "ca": "CA",
    "au": "AU",
    "us": "US",
    "ie": "IE",
    "se": "SE",
    "pl": "PL",
}
COUNTRY_ALIASES = {
    "UNITED STATES": "US",
    "USA": "US",
    "UNITED KINGDOM": "GB",
    "UK": "GB",
    "ENGLAND": "GB",
    "GERMANY": "DE",
    "TURKEY": "TR",
    "TURKIYE": "TR",
    "NETHERLANDS": "NL",
    "FRANCE": "FR",
    "CANADA": "CA",
    "AUSTRALIA": "AU",
}
INTENT_WORDS = ("quote", "pricing", "price", "demo", "buy", "integration", "proposal", "budget")
TARGET_MARKETS = frozenset({"US", "GB", "DE", "NL", "CA", "AU", "IE", "SE"})


class LeadIn(BaseModel):
    """Payload a website form (or n8n / Make) posts to `/leads`."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="allow")

    email: EmailStr
    name: str | None = Field(default=None, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=64)
    budget_usd: int | None = Field(default=None, ge=0, le=10_000_000)
    message: str | None = Field(default=None, max_length=5000)
    source: str | None = Field(default="website-form", max_length=64)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


@dataclass(slots=True)
class Enrichment:
    company_domain: str | None
    country: str | None


@dataclass(slots=True)
class Score:
    total: int
    reasons: list[str] = field(default_factory=list)


def payload_hash(lead: LeadIn) -> str:
    canonical = json.dumps(
        lead.model_dump(mode="json", exclude_none=True), sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _domain_from_website(website: str | None) -> str | None:
    if not website:
        return None
    host = re.sub(r"^[a-z]+://", "", website.lower()).split("/")[0].split(":")[0]
    host = host.removeprefix("www.")
    return host or None


def enrich(lead: LeadIn) -> Enrichment:
    email_domain = lead.email.split("@", 1)[1]
    domain = (
        email_domain if email_domain not in FREE_EMAIL_DOMAINS else None
    ) or _domain_from_website(lead.website)

    country: str | None = None
    if lead.country:
        raw = lead.country.upper()
        country = COUNTRY_ALIASES.get(raw, raw if len(raw) == 2 else None)
    if country is None and domain:
        country = TLD_COUNTRY.get(domain.rsplit(".", 1)[-1])
    return Enrichment(company_domain=domain, country=country)


def score_lead(lead: LeadIn, enrichment: Enrichment) -> Score:
    s = Score(0)

    def add(points: int, reason: str) -> None:
        s.total += points
        s.reasons.append(f"+{points} {reason}")

    if lead.email.split("@", 1)[1] not in FREE_EMAIL_DOMAINS:
        add(30, "business email")
    if lead.company:
        add(10, "company given")
    if enrichment.company_domain and lead.website:
        add(5, "website given")
    if lead.budget_usd is not None:
        if lead.budget_usd >= 5000:
            add(25, "budget >= 5k")
        elif lead.budget_usd >= 1000:
            add(15, "budget >= 1k")
    message = (lead.message or "").lower()
    if len(message) >= 50:
        add(10, "detailed message")
    if any(word in message for word in INTENT_WORDS):
        add(15, "buying intent")
    if enrichment.country in TARGET_MARKETS:
        add(5, "target market")
    s.total = min(s.total, 100)
    return s


class LeadSink(Protocol):
    """Pushes a qualified lead downstream (HubSpot, Sheet, notification)."""

    async def handle(self, lead: Lead) -> None: ...


@dataclass(slots=True)
class LeadOutcome:
    lead: Lead
    duplicate: bool
    qualified: bool
    reasons: list[str]


async def ingest_lead(
    session: AsyncSession,
    payload: LeadIn,
    *,
    threshold: int,
    sink: LeadSink | None = None,
) -> LeadOutcome:
    digest = payload_hash(payload)
    existing = await session.scalar(
        select(Lead).where(Lead.email == payload.email, Lead.payload_hash == digest)
    )
    if existing is not None:
        log.info("lead_duplicate", lead_id=existing.id)
        return LeadOutcome(existing, True, existing.score >= threshold, [])

    enrichment = enrich(payload)
    score = score_lead(payload, enrichment)
    lead = Lead(
        email=payload.email,
        payload_hash=digest,
        name=payload.name,
        company=payload.company,
        company_domain=enrichment.company_domain,
        country=enrichment.country,
        message=payload.message,
        source=payload.source,
        score=score.total,
        status=LeadStatus.QUALIFIED if score.total >= threshold else LeadStatus.NEW,
        raw={**payload.model_dump(mode="json"), "score_reasons": score.reasons},
    )
    session.add(lead)
    try:
        await session.commit()
    except IntegrityError:
        # Same payload arrived concurrently: the other request won, return its row.
        await session.rollback()
        winner = await session.scalar(
            select(Lead).where(Lead.email == payload.email, Lead.payload_hash == digest)
        )
        assert winner is not None
        return LeadOutcome(winner, True, winner.score >= threshold, [])

    qualified = lead.status is LeadStatus.QUALIFIED
    log.info("lead_ingested", lead_id=lead.id, score=lead.score, qualified=qualified)
    if sink is not None:
        try:
            await sink.handle(lead)
        except Exception as exc:
            lead.status = LeadStatus.FAILED
            lead.raw = {**lead.raw, "sync_error": str(exc)[:500]}
            log.exception("lead_sink_failed", lead_id=lead.id)
        await session.commit()
    return LeadOutcome(lead, False, qualified, score.reasons)
