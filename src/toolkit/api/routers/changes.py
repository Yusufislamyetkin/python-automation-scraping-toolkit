from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from toolkit.api.schemas import ChangeOut
from toolkit.db.models import ChangeEvent
from toolkit.db.repositories import changes_since
from toolkit.db.session import session_scope

router = APIRouter(tags=["changes"])


def to_change_out(e: ChangeEvent) -> ChangeOut:
    return ChangeOut(
        id=e.id,
        type=e.type.value,
        product_id=e.product_id,
        product_title=e.product.title,
        product_url=e.product.url,
        source=e.product.source,
        old_value=e.old_value,
        new_value=e.new_value,
        pct_change=e.pct_change,
        created_at=e.created_at,
    )


@router.get("/changes", response_model=list[ChangeOut])
async def list_changes(
    session: Annotated[AsyncSession, Depends(session_scope)],
    since: Annotated[
        datetime | None, Query(description="ISO-8601 timestamp, e.g. 2026-10-30T00:00:00Z")
    ] = None,
    include_new: bool = False,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[ChangeOut]:
    events = await changes_since(session, since, include_new=include_new, limit=limit)
    return [to_change_out(e) for e in events]
