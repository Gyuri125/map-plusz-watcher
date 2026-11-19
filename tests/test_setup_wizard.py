from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from allampapir_ertesito.setup_wizard import (
    _set_section_enabled,
    _update_env_file,
    _validate_bot_token,
    _validate_webhook,
)


class SetupWizardTests(unittest.TestCase):
    def test_validate_webhook(self) -> None:
        self.assertTrue(
            _validate_webhook("https://discord.com/api/webhooks/123/abc")
        )
        self.assertFalse(_validate_webhook("http://example.com/hook"))
        self.assertFalse(_validate_webhook("https://example.com/hook"))

    def test_validate_bot_token(self) -> None:
        self.assertTrue(_validate_bot_token("123456:ABC_def-123"))
        self.assertFalse(_validate_bot_token("abc"))
        self.assertFalse(_validate_bot_token("123456"))

    def test_update_env_file_preserves_other_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "# comment\nOTHER=value\nDISCORD_WEBHOOK_URL=old\n",
                encoding="utf-8",
            )
            _update_env_file(
                path,
                {
                    "DISCORD_WEBHOOK_URL": "https://new",
                    "TELEGRAM_CHAT_ID": "42",
                },
            )
            text = path.read_text(encoding="utf-8")
        self.assertIn("# comment", text)
        self.assertIn("OTHER=value", text)
        self.assertIn("DISCORD_WEBHOOK_URL=https://new", text)
        self.assertIn("TELEGRAM_CHAT_ID=42", text)
        self.assertNotIn("DISCORD_WEBHOOK_URL=old", text)

    def test_set_section_enabled_only_touches_target(self) -> None:
        text = (
            "[app]\n"
            "first_run_notify = true\n\n"
            "[notifiers.console]\n"
            "enabled = true\n\n"
            "[notifiers.discord]\n"
            "enabled = false\n"
            "webhook_url = \"${DISCORD_WEBHOOK_URL}\"\n\n"
            "[notifiers.telegram]\n"
            "enabled = false\n"
        )
        updated = _set_section_enabled(text, "notifiers.discord", True)
        self.assertIn("[notifiers.discord]\nenabled = true", updated)
        self.assertIn("[notifiers.telegram]\nenabled = false", updated)
        self.assertIn("[notifiers.console]\nenabled = true", updated)

    def test_set_section_enabled_adds_missing_section(self) -> None:
        updated = _set_section_enabled("[app]\nfoo = 1\n", "notifiers.discord", True)
        self.assertIn("[notifiers.discord]\nenabled = true", updated)


if __name__ == "__main__":
    unittest.main()
