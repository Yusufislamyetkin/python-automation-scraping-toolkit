from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from toolkit.api.routers import changes, export, health, jobs, leads, products, stats
from toolkit.config import get_settings
from toolkit.logging import configure_logging
from toolkit.services.dispatch import JobDispatcher, build_dispatcher

DASHBOARD_DIR = Path(__file__).parent / "dashboard"


def create_app(dispatcher: JobDispatcher | None = None) -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.dispatcher = dispatcher or await build_dispatcher(settings)
        yield
        await app.state.dispatcher.close()

    app = FastAPI(
        title="Automation & Scraping Toolkit",
        version="0.1.0",
        description=(
            "Competitor price/stock monitoring and lead-to-CRM automation. "
            "POST endpoints require the `X-API-Key` header."
        ),
        lifespan=lifespan,
    )
    for module in (health, jobs, products, changes, leads, export, stats):
        app.include_router(module.router)

    app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse("/dashboard/")

    return app


app = create_app()
