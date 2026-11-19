"""Telegram bot értesítés."""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.request

from ..config import TelegramSettings
from ..messages import PRODUCT_PAGE, WEBKINCSTAR_URL
from ..models import Message
from ..util import truncate
from .base import Notifier, NotifierError

_LABEL_LINE = re.compile(r"^(\s*)([^:\n]{1,60}):\s*(.*)$")


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

        plain_body = truncate(message.body, 2500)
        html_text = (
            f"<b>{html.escape(message.title)}</b>\n\n"
            f"{self._format_html(plain_body)}"
        )
        payload: dict[str, object] = {
            "chat_id": settings.chat_id,
            "disable_web_page_preview": False,
        }
        if len(html_text) <= 4000:
            payload["text"] = html_text
            payload["parse_mode"] = "HTML"
        else:
            # Ha valamiért túl hosszú lenne, inkább sima szöveget küldünk,
            # mert a csonkított HTML könnyen érvénytelen lenne.
            payload["text"] = truncate(
                f"{message.title}\n\n{message.body}",
                4000,
            )

        keyboard = self._keyboard(message)
        if keyboard:
            payload["reply_markup"] = {"inline_keyboard": keyboard}

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

    @staticmethod
    def _format_html(body: str) -> str:
        lines: list[str] = []
        for line in body.splitlines():
            if not line.strip():
                lines.append("")
                continue
            if line.lstrip().startswith(("http://", "https://")):
                lines.append(html.escape(line))
                continue
            match = _LABEL_LINE.match(line)
            if match:
                indent, label, value = match.groups()
                lines.append(
                    f"{indent}<b>{html.escape(label)}:</b> {html.escape(value)}"
                )
            else:
                lines.append(html.escape(line))
        return "\n".join(lines)

    @staticmethod
    def _keyboard(message: Message) -> list[list[dict[str, str]]]:
        series = message.series
        if series is None:
            return []
        first_row: list[dict[str, str]] = [
            {"text": "WebKincstár", "url": WEBKINCSTAR_URL}
        ]
        if series.pdf_url:
            first_row.append({"text": "Ajánlattétel", "url": series.pdf_url})
        return [
            first_row,
            [{"text": "AKK termékoldal", "url": PRODUCT_PAGE}],
        ]

    def _redact(self, text: str) -> str:
        token = self.settings.bot_token
        if token:
            return text.replace(token, "***")
        return text
