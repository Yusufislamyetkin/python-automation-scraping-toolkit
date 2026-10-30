from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from toolkit.api.schemas import JobOut, StatsOut
from toolkit.db.base import utcnow
from toolkit.db.models import ChangeEvent, ChangeType, JobRun, Lead, LeadStatus, Product
from toolkit.db.session import session_scope

router = APIRouter(tags=["dashboard"])


@router.get("/stats", response_model=StatsOut)
async def stats(session: Annotated[AsyncSession, Depends(session_scope)]) -> StatsOut:
    """Headline numbers for the dashboard."""
    now = utcnow()
    total = await session.scalar(select(func.count()).select_from(Product)) or 0
    in_stock = (
        await session.scalar(select(func.count()).select_from(Product).where(Product.in_stock)) or 0
    )
    rows = await session.execute(
        select(ChangeEvent.type, func.count())
        .where(
            ChangeEvent.created_at >= now - timedelta(hours=24),
            ChangeEvent.type != ChangeType.NEW_PRODUCT,
        )
        .group_by(ChangeEvent.type)
    )
    week = now - timedelta(days=7)
    leads = await session.scalar(
        select(func.count()).select_from(Lead).where(Lead.created_at >= week)
    )
    qualified = await session.scalar(
        select(func.count())
        .select_from(Lead)
        .where(
            Lead.created_at >= week,
            Lead.status.in_([LeadStatus.QUALIFIED, LeadStatus.SYNCED]),
        )
    )
    last = await session.scalar(
        select(JobRun).where(JobRun.finished_at.is_not(None)).order_by(JobRun.finished_at.desc())
    )
    return StatsOut(
        products_total=total,
        in_stock=in_stock,
        out_of_stock=total - in_stock,
        changes_24h={t.value: n for t, n in rows.all()},
        leads_7d=leads or 0,
        qualified_7d=qualified or 0,
        last_run=JobOut.model_validate(last) if last else None,
    )
