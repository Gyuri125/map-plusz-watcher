from __future__ import annotations

import io
import json
import unittest
import urllib.error
from datetime import date, datetime
from unittest.mock import patch

from allampapir_ertesito.config import (
    DiscordSettings,
    NtfySettings,
    TelegramSettings,
    WebhookSettings,
)
from allampapir_ertesito.messages import build_announcement
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
        self.assertEqual(payload["parse_mode"], "HTML")
        self.assertIn("<b>Új sorozat</b>", payload["text"])
        buttons = [
            button
            for row in payload["reply_markup"]["inline_keyboard"]
            for button in row
        ]
        labels = [button["text"] for button in buttons]
        self.assertIn("WebKincstár", labels)
        self.assertIn("Ajánlattétel", labels)
        self.assertIn("Dashboard", labels)
        self.assertIn("Naptárba", labels)
        self.assertIn("123:abc", request.full_url)

    def test_telegram_html_label_formatting(self) -> None:
        formatted = TelegramNotifier._format_html("  Kamat: 5,00% - 6,00%")
        self.assertEqual(formatted, "  <b>Kamat:</b> 5,00% - 6,00%")
        self.assertEqual(
            TelegramNotifier._format_html("https://example.com"),
            "https://example.com",
        )

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
        self.assertEqual(embed["fields"][0]["name"], "Sorozat")
        labels = [button["label"] for button in payload["components"][0]["components"]]
        self.assertIn("WebKincstár", labels)
        self.assertIn("Dashboard", labels)
        self.assertIn("Naptárba", labels)
        self.assertIn("with_components=true", urlopen.call_args[0][0].full_url)

    @patch("allampapir_ertesito.notifiers.discord.urllib.request.urlopen")
    def test_discord_retries_without_components_on_400(self, urlopen) -> None:
        error = urllib.error.HTTPError(
            "https://discord.com/api/webhooks/123/abc?with_components=true",
            400,
            "Bad Request",
            {},
            io.BytesIO(b'{"message":"Invalid components"}'),
        )
        urlopen.side_effect = [error, FakeResponse()]
        settings = DiscordSettings(
            enabled=True,
            webhook_url="https://discord.com/api/webhooks/123/abc",
        )
        DiscordNotifier(settings).send(sample_message())
        self.assertEqual(urlopen.call_count, 2)
        first_request = urlopen.call_args_list[0][0][0]
        second_request = urlopen.call_args_list[1][0][0]
        self.assertIn("with_components=true", first_request.full_url)
        self.assertNotIn("with_components", second_request.full_url)
        second_payload = json.loads(second_request.data.decode("utf-8"))
        self.assertNotIn("components", second_payload)

    @patch("allampapir_ertesito.notifiers.discord.urllib.request.urlopen")
    def test_discord_real_announcement_has_countdown_and_fields(self, urlopen) -> None:
        urlopen.return_value = FakeResponse()
        offering = make_offering(
            "2031/M7",
            date(2027, 1, 4),
            date(2027, 3, 31),
            published=datetime(2026, 12, 28, 13, 30),
        )
        retail = make_retail("2031/M7", date(2027, 1, 4), date(2027, 3, 31))
        series = SeriesInfo.from_offering(offering, retail)
        message = build_announcement(series, date(2026, 12, 28))
        settings = DiscordSettings(
            enabled=True,
            webhook_url="https://discord.com/api/webhooks/123/abc",
        )
        DiscordNotifier(settings).send(message)
        payload = json.loads(urlopen.call_args[0][0].data.decode("utf-8"))
        embed = payload["embeds"][0]
        self.assertIn("Kezdésig: 7 nap", embed["description"])
        names = [field["name"] for field in embed["fields"]]
        self.assertIn("Kihirdetve", names)
        self.assertIn("Linkek", names)
        self.assertIn("Fizetés", names)
        labels = [button["label"] for button in payload["components"][0]["components"]]
        self.assertIn("Ajánlattétel", labels)

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
