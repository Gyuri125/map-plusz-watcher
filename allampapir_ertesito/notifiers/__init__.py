"""Az értesítési csatornák összeállítása a konfigurációból."""

from __future__ import annotations

from ..config import Config
from .base import DispatchResult, Notifier, NotifierError, NotifierManager
from .console import ConsoleNotifier
from .discord import DiscordNotifier
from .email import EmailNotifier
from .ntfy import NtfyNotifier
from .telegram import TelegramNotifier
from .webhook import WebhookNotifier
from .windows import WindowsNotifier


def build_notifiers(config: Config) -> list[Notifier]:
    notifiers: list[Notifier] = []
    timeout = config.app.http_timeout_seconds
    if config.console.enabled:
        notifiers.append(ConsoleNotifier())
    if config.email.enabled:
        notifiers.append(EmailNotifier(config.email))
    if config.telegram.enabled:
        notifiers.append(TelegramNotifier(config.telegram, timeout=timeout))
    if config.discord.enabled:
        notifiers.append(DiscordNotifier(config.discord, timeout=timeout))
    if config.ntfy.enabled:
        notifiers.append(NtfyNotifier(config.ntfy, timeout=timeout))
    if config.windows.enabled:
        notifiers.append(WindowsNotifier(config.windows))
    if config.webhook.enabled:
        notifiers.append(WebhookNotifier(config.webhook, timeout=timeout))
    return notifiers


__all__ = [
    "build_notifiers",
    "DispatchResult",
    "Notifier",
    "NotifierError",
    "NotifierManager",
]
