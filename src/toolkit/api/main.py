from fastapi import FastAPI

from toolkit.api.routers import health
from toolkit.config import get_settings
from toolkit.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    app = FastAPI(
        title="Automation & Scraping Toolkit",
        version="0.1.0",
        description="Competitor price/stock monitoring and lead-to-CRM automation.",
    )
    app.include_router(health.router)
    return app


app = create_app()
