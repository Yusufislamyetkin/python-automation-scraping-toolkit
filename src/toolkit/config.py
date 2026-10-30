"""Application settings loaded from environment variables / `.env`."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    log_level: str = "INFO"
    log_json: bool = True

    database_url: str = "postgresql+asyncpg://toolkit:toolkit@localhost:5434/toolkit"
    redis_url: str = "redis://localhost:6379/0"

    api_key: SecretStr = SecretStr("change-me")

    # Scraping
    user_agent: str = "PriceMonitorBot/0.1 (+https://github.com/Yusufislamyetkin/python-automation-scraping-toolkit)"
    request_delay_seconds: float = 1.0
    max_concurrency: int = 4
    max_pages: int = 5
    books_fetch_details: bool = False
    http_timeout_seconds: float = 20.0
    proxy_url: str | None = None
    respect_robots_txt: bool = True
    snapshot_dir: Path = Path("data/snapshots")

    # Scheduler
    schedule_hour_utc: int = 6
    schedule_targets: list[str] = Field(default_factory=lambda: ["books"])

    # Change detection
    price_change_threshold_pct: float = 0.0

    # Leads
    lead_score_threshold: int = 60

    # Demo-mode output
    demo_output_dir: Path = Path("data/demo")

    # Google Sheets
    google_service_account_file: Path | None = None
    google_sheet_id: str | None = None

    # HubSpot
    hubspot_token: SecretStr | None = None
    hubspot_base_url: str = "https://api.hubapi.com"

    # Notifications
    slack_webhook_url: SecretStr | None = None
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None

    # SMTP fallback
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = None
    alert_email_to: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
