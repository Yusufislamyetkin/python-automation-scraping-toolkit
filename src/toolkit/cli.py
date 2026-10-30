"""Typer CLI entry point (`toolkit ...`)."""

import asyncio
import random
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy import select

from toolkit.config import get_settings
from toolkit.db.models import Product
from toolkit.db.repositories import all_products
from toolkit.db.session import get_sessionmaker
from toolkit.integrations.factory import build_change_sink
from toolkit.logging import configure_logging
from toolkit.services.export import to_csv, write_xlsx
from toolkit.services.jobs import create_job, run_scrape_job

app = typer.Typer(help="Price monitoring & lead automation toolkit.", no_args_is_help=True)


class ExportFormat(StrEnum):
    csv = "csv"
    xlsx = "xlsx"


@app.callback()
def main() -> None:
    """Price monitoring & lead automation toolkit."""
    s = get_settings()
    configure_logging(s.log_level, json=False)


@app.command()
def version() -> None:
    """Print the toolkit version."""
    typer.echo("0.1.0")


@app.command()
def scrape(
    target: Annotated[str, typer.Argument(help="books | quotes")],
    pages: Annotated[int | None, typer.Option(help="Override MAX_PAGES")] = None,
) -> None:
    """Run one scrape now (no queue), store history and detect changes."""
    if target not in ("books", "quotes"):
        raise typer.BadParameter("target must be 'books' or 'quotes'")
    settings = get_settings()
    if pages is not None:
        settings = settings.model_copy(update={"max_pages": pages})

    async def _run() -> None:
        sm = get_sessionmaker()
        async with sm() as session:
            job = await create_job(session, "scrape", target)
        done = await run_scrape_job(job.id, settings, sm, sink=build_change_sink(settings))
        typer.echo(
            f"job {done.id} {done.status.value}: {done.items_ok} ok, "
            f"{done.items_failed} failed, {done.meta.get('change_events', 0)} change events, "
            f"{done.duration_ms} ms"
        )

    asyncio.run(_run())


@app.command()
def export(
    format: Annotated[ExportFormat, typer.Option("--format", "-f")] = ExportFormat.csv,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export the product catalogue to CSV or XLSX."""
    path = output or Path(f"data/exports/products.{format.value}")

    async def _run() -> int:
        async with get_sessionmaker()() as session:
            products = await all_products(session)
        if format is ExportFormat.xlsx:
            write_xlsx(products, path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(to_csv(products), encoding="utf-8", newline="")
        return len(products)

    count = asyncio.run(_run())
    typer.echo(f"wrote {count} products to {path}")


@app.command("simulate-drift")
def simulate_drift(
    count: Annotated[int, typer.Option(help="How many stored products to alter")] = 5,
    seed: Annotated[int | None, typer.Option()] = None,
) -> None:
    """DEMO ONLY: nudge stored prices/stock so the next scrape produces change events.

    The sandbox target sites never change their prices, so without this you
    would never see a price-drop alert in a demo.
    """
    rng = random.Random(seed)

    async def _run() -> int:
        async with get_sessionmaker()() as session:
            products = list(
                (await session.scalars(select(Product).where(Product.source == "books"))).all()
            )
            picked = rng.sample(products, min(count, len(products)))
            for i, p in enumerate(picked):
                if i % 3 == 2:
                    p.in_stock = not p.in_stock
                elif p.current_price is not None:
                    factor = Decimal("1.15") if i % 3 == 0 else Decimal("0.85")
                    p.current_price = (p.current_price * factor).quantize(Decimal("0.01"))
            await session.commit()
            return len(picked)

    typer.echo(f"altered {asyncio.run(_run())} stored products; run `toolkit scrape books` next")


if __name__ == "__main__":
    app()
