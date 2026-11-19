"""Általános JSON webhook értesítés."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

from ..config import WebhookSettings
from ..models import Message
from .base import Notifier, NotifierError


class WebhookNotifier(Notifier):
    name = "webhook"

    def __init__(self, settings: WebhookSettings, timeout: int = 30) -> None:
        self.settings = settings
        self.timeout = timeout

    def send(self, message: Message) -> None:
        if not self.settings.url:
            raise NotifierError("Nincs beállítva webhook URL.")

        payload = {
            "source": "allampapir-ertesito",
            "event": message.event,
            "title": message.title,
            "message": message.body,
            "series": message.series.to_dict() if message.series else None,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json; charset=utf-8"}
        headers.update(self.settings.headers)
        request = urllib.request.Request(
            self.settings.url,
            data=data,
            method="POST",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response.read(500)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(500).decode("utf-8", "replace").strip()
            except OSError:
                pass
            raise NotifierError(
                f"Webhook HTTP {exc.code}: {self._redact(detail or str(exc.reason))}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise NotifierError(
                f"Webhook hálózati hiba: {self._redact(str(exc))}"
            ) from exc

    def _redact(self, text: str) -> str:
        url = self.settings.url
        if url:
            return text.replace(url, "***")
        return text
