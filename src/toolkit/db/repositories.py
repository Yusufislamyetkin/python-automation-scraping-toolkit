"""Read-side queries shared by the API, CLI and integrations."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from toolkit.db.models import ChangeEvent, ChangeType, PriceSnapshot, Product


async def list_products(
    session: AsyncSession,
    *,
    source: str | None = None,
    in_stock: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[Product]:
    stmt = select(Product).order_by(Product.source, Product.id).limit(limit).offset(offset)
    if source:
        stmt = stmt.where(Product.source == source)
    if in_stock is not None:
        stmt = stmt.where(Product.in_stock == in_stock)
    return (await session.scalars(stmt)).all()


async def all_products(session: AsyncSession) -> Sequence[Product]:
    return (await session.scalars(select(Product).order_by(Product.source, Product.id))).all()


async def product_history(
    session: AsyncSession, product_id: int, limit: int = 500
) -> Sequence[PriceSnapshot]:
    stmt = (
        select(PriceSnapshot)
        .where(PriceSnapshot.product_id == product_id)
        .order_by(PriceSnapshot.scraped_at.desc())
        .limit(limit)
    )
    return (await session.scalars(stmt)).all()


async def changes_since(
    session: AsyncSession,
    since: datetime | None,
    *,
    include_new: bool = False,
    limit: int = 500,
) -> Sequence[ChangeEvent]:
    stmt = (
        select(ChangeEvent)
        .options(selectinload(ChangeEvent.product))
        .order_by(ChangeEvent.created_at.desc(), ChangeEvent.id.desc())
        .limit(limit)
    )
    if since is not None:
        stmt = stmt.where(ChangeEvent.created_at >= since)
    if not include_new:
        stmt = stmt.where(ChangeEvent.type != ChangeType.NEW_PRODUCT)
    return (await session.scalars(stmt)).all()
