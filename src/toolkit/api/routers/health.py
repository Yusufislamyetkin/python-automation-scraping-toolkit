from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from toolkit.config import Settings, get_settings
from toolkit.db.session import session_scope
from toolkit.integrations.factory import integration_modes

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(
    session: Annotated[AsyncSession, Depends(session_scope)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    try:
        await session.execute(text("SELECT 1"))
        db = "ok"
    except Exception:
        db = "unavailable"
    return {
        "status": "ok" if db == "ok" else "degraded",
        "database": db,
        "integrations": integration_modes(settings),
    }
