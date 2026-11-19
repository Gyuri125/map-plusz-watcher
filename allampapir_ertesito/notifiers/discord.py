"""Discord webhook értesítés."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from ..config import DiscordSettings
from ..messages import PRODUCT_PAGE
from ..models import Message
from ..util import truncate
from .base import Notifier, NotifierError

_COLORS = {
    "announcement": 0x3498DB,  # kék
    "start": 0x2ECC71,  # zöld
    "reminder": 0xE67E22,  # narancs
    "error": 0xE74C3C,  # piros
    "first_run": 0x9B59B6,  # lila
    "test": 0x95A5A6,  # szürke
}


class DiscordNotifier(Notifier):
    name = "discord"

    def __init__(self, settings: DiscordSettings, timeout: int = 30) -> None:
        self.settings = settings
        self.timeout = timeout

    def send(self, message: Message) -> None:
        if not self.settings.webhook_url:
            raise NotifierError("Nincs beállítva Discord webhook URL.")

        embed: dict[str, object] = {
            "title": truncate(message.title, 256),
            "description": truncate(message.body, 4096),
            "color": _COLORS.get(message.event, 0x3498DB),
            "footer": {"text": "MÁP+ értesítő"},
        }
        if message.series is not None:
            embed["url"] = message.series.pdf_url or PRODUCT_PAGE

        payload: dict[str, object] = {
            "username": self.settings.username or "MÁP+ értesítő",
            "embeds": [embed],
            "allowed_mentions": {"parse": []},
        }
        if self.settings.avatar_url:
            payload["avatar_url"] = self.settings.avatar_url

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.settings.webhook_url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response.read(200)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(500).decode("utf-8", "replace").strip()
            except OSError:
                pass
            raise NotifierError(
                f"Discord HTTP {exc.code}: {self._redact(detail or exc.reason)}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise NotifierError(
                f"Discord hálózati hiba: {self._redact(str(exc))}"
            ) from exc

    def _redact(self, text: str) -> str:
        url = self.settings.webhook_url
        if url:
            return text.replace(url, "***")
        return text
