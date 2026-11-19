"""Telegram bot értesítés."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from ..config import TelegramSettings
from ..models import Message
from ..util import truncate
from .base import Notifier, NotifierError


class TelegramNotifier(Notifier):
    name = "telegram"

    def __init__(self, settings: TelegramSettings, timeout: int = 30) -> None:
        self.settings = settings
        self.timeout = timeout

    def send(self, message: Message) -> None:
        settings = self.settings
        if not settings.bot_token:
            raise NotifierError("Nincs beállítva Telegram bot token.")
        if not settings.chat_id:
            raise NotifierError("Nincs beállítva Telegram chat_id.")

        text = truncate(f"{message.title}\n\n{message.body}", 4000)
        payload: dict[str, object] = {
            "chat_id": settings.chat_id,
            "text": text,
            "disable_web_page_preview": False,
        }
        if settings.message_thread_id > 0:
            payload["message_thread_id"] = settings.message_thread_id

        url = f"https://api.telegram.org/bot{settings.bot_token}/sendMessage"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(500).decode("utf-8", "replace")
            except OSError:
                pass
            raise NotifierError(
                f"Telegram HTTP {exc.code}: {self._redact(detail)}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise NotifierError(f"Telegram hálózati hiba: {exc}") from exc

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise NotifierError(
                f"A Telegram nem JSON választ adott: {self._redact(body[:200])}"
            ) from exc
        if not parsed.get("ok"):
            description = parsed.get("description") or "ismeretlen hiba"
            raise NotifierError(f"Telegram hiba: {self._redact(str(description))}")

    def _redact(self, text: str) -> str:
        token = self.settings.bot_token
        if token:
            return text.replace(token, "***")
        return text
