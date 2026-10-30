"""CSV / XLSX export of the product catalogue."""

import csv
import io
from collections.abc import Sequence
from pathlib import Path

from openpyxl import Workbook

from toolkit.db.models import Product

COLUMNS = [
    "id",
    "source",
    "external_id",
    "title",
    "category",
    "currency",
    "current_price",
    "in_stock",
    "stock_count",
    "url",
    "last_seen_at",
]


def product_rows(products: Sequence[Product]) -> list[list[str]]:
    rows: list[list[str]] = []
    for p in products:
        rows.append(
            [
                str(p.id),
                p.source,
                p.external_id,
                p.title,
                p.category or "",
                p.currency,
                "" if p.current_price is None else f"{p.current_price:.2f}",
                "yes" if p.in_stock else "no",
                "" if p.stock_count is None else str(p.stock_count),
                p.url,
                p.last_seen_at.isoformat() if p.last_seen_at else "",
            ]
        )
    return rows


def to_csv(products: Sequence[Product]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(COLUMNS)
    writer.writerows(product_rows(products))
    return buf.getvalue()


def write_xlsx(products: Sequence[Product], path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "products"
    ws.append(COLUMNS)
    for row in product_rows(products):
        ws.append(row)
    ws.freeze_panes = "A2"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
