import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProductOut(ORM):
    id: int
    source: str
    external_id: str
    title: str
    url: str
    category: str | None
    currency: str
    current_price: Decimal | None
    in_stock: bool
    stock_count: int | None
    extra: dict[str, Any]
    first_seen_at: datetime
    last_seen_at: datetime


class SnapshotOut(ORM):
    price: Decimal | None
    in_stock: bool
    stock_count: int | None
    scraped_at: datetime
    job_run_id: uuid.UUID | None


class ChangeOut(BaseModel):
    id: int
    type: str
    product_id: int
    product_title: str
    product_url: str
    source: str
    old_value: str | None
    new_value: str | None
    pct_change: Decimal | None
    created_at: datetime


class JobOut(ORM):
    id: uuid.UUID
    job_type: str
    target: str | None
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    items_total: int
    items_ok: int
    items_failed: int
    error: str | None
    meta: dict[str, Any]
    created_at: datetime


class JobWithChanges(JobOut):
    changes: list[ChangeOut] = []


class LeadOut(BaseModel):
    id: int
    email: str
    score: int
    status: str
    qualified: bool
    duplicate: bool
    company_domain: str | None
    country: str | None
    score_reasons: list[str]
