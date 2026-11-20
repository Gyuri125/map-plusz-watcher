"""Telegram getUpdates segédek a csoport chat_id felderítéséhez."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

USER_AGENT = "AllampapirErtesito/1.0 (telegram chat id helper)"


class TelegramUtilError(RuntimeError):
    """A Telegram API nem elérhető vagy hibás választ adott."""


def _redact(text: str, token: str) -> str:
    return text.replace(token, "***") if token else text


def fetch_updates(token: str, timeout: int = 30) -> dict[str, Any]:
    """Lekéri a bothoz érkezett, még fel nem dolgozott update-eket."""
    if not token:
        raise TelegramUtilError("Nincs Telegram bot token.")
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read(500).decode("utf-8", "replace").strip()
        except OSError:
            pass
        raise TelegramUtilError(
            f"Telegram HTTP {exc.code}: {_redact(detail or str(exc.reason), token)}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TelegramUtilError(
            f"Telegram hálózati hiba: {_redact(str(exc), token)}"
        ) from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TelegramUtilError(
            f"A Telegram nem JSON választ adott: {_redact(raw[:200], token)}"
        ) from exc
    if not isinstance(payload, dict) or not payload.get("ok"):
        description = payload.get("description") if isinstance(payload, dict) else None
        raise TelegramUtilError(
            f"Telegram hiba: {_redact(str(description or 'ismeretlen hiba'), token)}"
        )
    return payload


def extract_chats(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """A getUpdates válaszból kinyeri az egyedi chat-eket.

    A bot hozzáadásakor keletkező ``my_chat_member`` update-ből is kiolvassa
    a csoportot, így akkor is működik, ha a bot még nem kapott sima üzenetet.
    """
    chats: dict[int, dict[str, Any]] = {}
    for update in payload.get("result", []) or []:
        if not isinstance(update, dict):
            continue
        for key in (
            "message",
            "edited_message",
            "channel_post",
            "edited_channel_post",
            "my_chat_member",
            "chat_member",
            "chat_join_request",
        ):
            candidate = update.get(key)
            if not isinstance(candidate, dict):
                continue
            chat = candidate.get("chat")
            if not isinstance(chat, dict):
                continue
            chat_id = chat.get("id")
            if chat_id is None:
                continue
            title = (
                chat.get("title")
                or chat.get("username")
                or chat.get("first_name")
                or chat.get("last_name")
                or ""
            )
            chats[int(chat_id)] = {
                "id": int(chat_id),
                "type": str(chat.get("type") or ""),
                "title": str(title),
            }
    return sorted(chats.values(), key=lambda item: (item["id"] >= 0, item["id"]))
