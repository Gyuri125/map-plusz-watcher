"""ntfy.sh push értesítés (ingyenes, mobilra is)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from ..config import NtfySettings
from ..models import Message
from ..util import truncate
from .base import Notifier, NotifierError


class NtfyNotifier(Notifier):
    name = "ntfy"

    def __init__(self, settings: NtfySettings, timeout: int = 30) -> None:
        self.settings = settings
        self.timeout = timeout

    def send(self, message: Message) -> None:
        settings = self.settings
        if not settings.topic:
            raise NotifierError("Nincs beállítva ntfy téma.")

        payload: dict[str, object] = {
            "topic": settings.topic,
            "title": truncate(message.title, 250),
            "message": truncate(message.body, 4000),
            "priority": settings.priority,
        }
        if settings.tags:
            payload["tags"] = list(settings.tags)
        if settings.click_url:
            payload["click"] = settings.click_url

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if settings.token:
            headers["Authorization"] = f"Bearer {settings.token}"

        url = settings.url.rstrip("/")
        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers=headers,
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
                f"ntfy HTTP {exc.code}: {detail or exc.reason}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise NotifierError(f"ntfy hálózati hiba: {exc}") from exc
