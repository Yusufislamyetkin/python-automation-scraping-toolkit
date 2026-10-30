"""Alerts: Slack incoming webhook and/or Telegram bot, with SMTP email as fallback."""

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Protocol

import httpx

from toolkit.logging import get_logger

log = get_logger(__name__)


class Notifier(Protocol):
    name: str

    async def send(self, subject: str, text: str) -> None: ...


class SlackWebhookNotifier:
    name = "slack"

    def __init__(self, webhook_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._url = webhook_url
        self._client = client or httpx.AsyncClient(timeout=10)

    async def send(self, subject: str, text: str) -> None:
        resp = await self._client.post(self._url, json={"text": f"*{subject}*\n{text}"})
        resp.raise_for_status()


class TelegramNotifier:
    name = "telegram"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        client: httpx.AsyncClient | None = None,
        base_url: str = "https://api.telegram.org",
    ) -> None:
        self._url = f"{base_url}/bot{bot_token}/sendMessage"
        self._chat_id = chat_id
        self._client = client or httpx.AsyncClient(timeout=10)

    async def send(self, subject: str, text: str) -> None:
        resp = await self._client.post(
            self._url,
            json={"chat_id": self._chat_id, "text": f"{subject}\n{text}"[:4000]},
        )
        resp.raise_for_status()


class SmtpEmailNotifier:
    name = "email"

    def __init__(
        self,
        host: str,
        port: int,
        sender: str,
        recipient: str,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        self._host, self._port = host, port
        self._sender, self._recipient = sender, recipient
        self._user, self._password = user, password

    def _send_sync(self, subject: str, text: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self._sender, self._recipient, subject
        msg.set_content(text)
        with smtplib.SMTP(self._host, self._port, timeout=20) as smtp:
            smtp.starttls()
            if self._user and self._password:
                smtp.login(self._user, self._password)
            smtp.send_message(msg)

    async def send(self, subject: str, text: str) -> None:
        await asyncio.to_thread(self._send_sync, subject, text)


class LogNotifier:
    """Demo mode: nothing configured, so log the message instead of sending it."""

    name = "log"

    async def send(self, subject: str, text: str) -> None:
        log.info("would_send_alert", mode="demo", subject=subject, text=text)


class FakeNotifier:
    def __init__(self, name: str = "fake", fail: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.sent: list[tuple[str, str]] = []

    async def send(self, subject: str, text: str) -> None:
        if self.fail:
            raise RuntimeError(f"{self.name} down")
        self.sent.append((subject, text))


class FallbackNotifier:
    """Sends to every primary channel; if none succeeded, uses the fallback."""

    name = "fallback"

    def __init__(self, primaries: list[Notifier], fallback: Notifier) -> None:
        self._primaries = primaries
        self._fallback = fallback

    async def send(self, subject: str, text: str) -> None:
        delivered = 0
        for channel in self._primaries:
            try:
                await channel.send(subject, text)
                delivered += 1
            except Exception as exc:
                log.warning("alert_channel_failed", channel=channel.name, error=str(exc))
        if delivered == 0:
            log.info("alert_fallback", channel=self._fallback.name)
            await self._fallback.send(subject, text)
