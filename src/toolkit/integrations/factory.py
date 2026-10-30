"""Wires integration clients from settings.

Anything without credentials falls back to demo mode (local CSV + "would send"
log lines), so the whole pipeline runs on a laptop with zero accounts.
"""

from toolkit.config import Settings
from toolkit.db.session import get_sessionmaker
from toolkit.integrations.hubspot import DemoHubSpotClient, HttpHubSpotClient, HubSpotClient
from toolkit.integrations.notifier import (
    FallbackNotifier,
    LogNotifier,
    Notifier,
    SlackWebhookNotifier,
    SmtpEmailNotifier,
    TelegramNotifier,
)
from toolkit.integrations.sheets import CsvSheetsClient, GspreadSheetsClient, SheetsClient
from toolkit.integrations.sinks import AlertingChangeSink, CrmLeadSink
from toolkit.logging import get_logger

log = get_logger(__name__)

_cache: dict[str, object] = {}


def build_sheets(settings: Settings) -> SheetsClient:
    if settings.google_service_account_file and settings.google_sheet_id:
        if "sheets" not in _cache:
            _cache["sheets"] = GspreadSheetsClient(
                settings.google_service_account_file, settings.google_sheet_id
            )
        return _cache["sheets"]  # type: ignore[return-value]
    return CsvSheetsClient(settings.demo_output_dir)


def build_hubspot(settings: Settings) -> HubSpotClient:
    if settings.hubspot_token:
        key = f"hubspot:{id(settings)}"
        if key not in _cache:
            _cache[key] = HttpHubSpotClient(
                settings.hubspot_token.get_secret_value(), settings.hubspot_base_url
            )
        return _cache[key]  # type: ignore[return-value]
    return DemoHubSpotClient(settings.demo_output_dir)


def build_notifier(settings: Settings) -> Notifier:
    key = f"notifier:{id(settings)}"
    if key not in _cache:
        _cache[key] = _make_notifier(settings)
    return _cache[key]  # type: ignore[return-value]


def _make_notifier(settings: Settings) -> Notifier:
    primaries: list[Notifier] = []
    if settings.slack_webhook_url:
        primaries.append(SlackWebhookNotifier(settings.slack_webhook_url.get_secret_value()))
    if settings.telegram_bot_token and settings.telegram_chat_id:
        primaries.append(
            TelegramNotifier(
                settings.telegram_bot_token.get_secret_value(), settings.telegram_chat_id
            )
        )
    fallback: Notifier = LogNotifier()
    if settings.smtp_host and settings.smtp_from and settings.alert_email_to:
        fallback = SmtpEmailNotifier(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_from,
            settings.alert_email_to,
            settings.smtp_user,
            settings.smtp_password.get_secret_value() if settings.smtp_password else None,
        )
    return FallbackNotifier(primaries, fallback)


def integration_modes(settings: Settings) -> dict[str, str]:
    """What is live vs demo; shown by `/health` and logged at startup."""
    return {
        "sheets": "live"
        if settings.google_service_account_file and settings.google_sheet_id
        else "demo",
        "hubspot": "live" if settings.hubspot_token else "demo",
        "slack": "live" if settings.slack_webhook_url else "off",
        "telegram": "live" if settings.telegram_bot_token and settings.telegram_chat_id else "off",
        "email": "live" if settings.smtp_host and settings.alert_email_to else "demo",
    }


def build_change_sink(settings: Settings) -> AlertingChangeSink:
    return AlertingChangeSink(build_sheets(settings), build_notifier(settings), get_sessionmaker())


def build_lead_sink(settings: Settings) -> CrmLeadSink:
    return CrmLeadSink(build_sheets(settings), build_hubspot(settings), build_notifier(settings))
