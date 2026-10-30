from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from toolkit.db.repositories import all_products
from toolkit.db.session import session_scope
from toolkit.services.export import to_csv

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/products.csv", response_class=Response)
async def export_products_csv(
    session: Annotated[AsyncSession, Depends(session_scope)],
) -> Response:
    body = to_csv(await all_products(session))
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="products.csv"'},
    )
