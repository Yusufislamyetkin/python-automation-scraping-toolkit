from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from toolkit.api.schemas import ProductOut, SnapshotOut
from toolkit.db.models import PriceSnapshot, Product
from toolkit.db.repositories import list_products, product_history
from toolkit.db.session import session_scope

router = APIRouter(prefix="/products", tags=["products"])

Session = Annotated[AsyncSession, Depends(session_scope)]


@router.get("", response_model=list[ProductOut])
async def get_products(
    session: Session,
    source: str | None = None,
    in_stock: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Sequence[Product]:
    return await list_products(
        session, source=source, in_stock=in_stock, limit=limit, offset=offset
    )


@router.get("/{product_id}/history", response_model=list[SnapshotOut])
async def get_history(product_id: int, session: Session) -> Sequence[PriceSnapshot]:
    if await session.get(Product, product_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "product not found")
    return await product_history(session, product_id)
