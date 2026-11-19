from __future__ import annotations

import json
import unittest
from datetime import date
from unittest.mock import patch

from allampapir_ertesito.config import (
    DiscordSettings,
    NtfySettings,
    TelegramSettings,
    WebhookSettings,
)
from allampapir_ertesito.models import Message, SeriesInfo
from allampapir_ertesito.notifiers.discord import DiscordNotifier
from allampapir_ertesito.notifiers.ntfy import NtfyNotifier
from allampapir_ertesito.notifiers.telegram import TelegramNotifier
from allampapir_ertesito.notifiers.webhook import WebhookNotifier
from tests.helpers import make_offering, make_retail


class FakeResponse:
    def __init__(self, body: bytes = b"{}") -> None:
        self.body = body

    def read(self, size: int | None = None) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def sample_message() -> Message:
    offering = make_offering("2031/M7", date(2027, 1, 4), date(2027, 3, 31))
    retail = make_retail("2031/M7", date(2027, 1, 4), date(2027, 3, 31))
    series = SeriesInfo.from_offering(offering, retail)
    return Message(event="announcement", title="Új sorozat", body="Részletek", series=series)


class NotifierTests(unittest.TestCase):
    @patch("allampapir_ertesito.notifiers.ntfy.urllib.request.urlopen")
    def test_ntfy_payload(self, urlopen) -> None:
        urlopen.return_value = FakeResponse()
        settings = NtfySettings(
            enabled=True,
            url="https://ntfy.sh",
            topic="test-topic",
            priority="high",
            tags=("moneybag",),
            click_url="https://example.com",
            token="titok",
        )
        NtfyNotifier(settings).send(sample_message())
        request = urlopen.call_args[0][0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["topic"], "test-topic")
        self.assertEqual(payload["title"], "Új sorozat")
        self.assertEqual(payload["priority"], "high")
        self.assertEqual(payload["click"], "https://example.com")
        headers = {k.lower(): v for k, v in request.header_items()}
        self.assertEqual(headers["authorization"], "Bearer titok")

    @patch("allampapir_ertesito.notifiers.telegram.urllib.request.urlopen")
    def test_telegram_payload(self, urlopen) -> None:
        urlopen.return_value = FakeResponse(b'{"ok": true}')
        settings = TelegramSettings(
            enabled=True,
            bot_token="123:abc",
            chat_id="456",
            message_thread_id=7,
        )
        TelegramNotifier(settings).send(sample_message())
        request = urlopen.call_args[0][0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["chat_id"], "456")
        self.assertEqual(payload["message_thread_id"], 7)
        self.assertIn("Új sorozat", payload["text"])
        self.assertIn("123:abc", request.full_url)

    @patch("allampapir_ertesito.notifiers.discord.urllib.request.urlopen")
    def test_discord_embed_payload(self, urlopen) -> None:
        urlopen.return_value = FakeResponse()
        settings = DiscordSettings(
            enabled=True,
            webhook_url="https://discord.com/api/webhooks/123/abc",
            username="MÁP+ teszt",
        )
        DiscordNotifier(settings).send(sample_message())
        request = urlopen.call_args[0][0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["username"], "MÁP+ teszt")
        self.assertEqual(payload["allowed_mentions"]["parse"], [])
        embed = payload["embeds"][0]
        self.assertIn("Új sorozat", embed["title"])
        self.assertIn("Részletek", embed["description"])
        self.assertTrue(embed["url"].endswith(".pdf"))

    @patch("allampapir_ertesito.notifiers.webhook.urllib.request.urlopen")
    def test_webhook_payload_contains_series(self, urlopen) -> None:
        urlopen.return_value = FakeResponse()
        settings = WebhookSettings(
            enabled=True,
            url="https://example.com/hook",
            headers={"X-Test": "1"},
        )
        WebhookNotifier(settings).send(sample_message())
        request = urlopen.call_args[0][0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["source"], "allampapir-ertesito")
        self.assertEqual(payload["event"], "announcement")
        self.assertEqual(payload["series"]["name"], "2031/M7")
        headers = {k.lower(): v for k, v in request.header_items()}
        self.assertEqual(headers["x-test"], "1")


if __name__ == "__main__":
    unittest.main()
