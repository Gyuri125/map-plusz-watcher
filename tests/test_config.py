from __future__ import annotations

import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from allampapir_ertesito.config import ConfigError, load_config


class ConfigTests(unittest.TestCase):
    def _write(self, directory: Path, content: str) -> Path:
        path = directory / "config.toml"
        path.write_text(textwrap.dedent(content), encoding="utf-8")
        return path

    def test_loads_example_config(self) -> None:
        example = Path(__file__).resolve().parent.parent / "config.example.toml"
        config = load_config(example)
        self.assertTrue(config.console.enabled)
        self.assertEqual(config.app.timezone, "Europe/Budapest")
        self.assertIn("console", config.enabled_notifier_names)

    def test_paths_are_resolved_relative_to_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = self._write(
                directory,
                """
                [app]
                state_file = "data/state.json"
                log_file = "logs/app.log"

                [notifiers.console]
                enabled = true
                """,
            )
            config = load_config(path)
            self.assertEqual(config.app.state_file, (directory / "data/state.json").resolve())
            self.assertEqual(config.app.log_file, (directory / "logs/app.log").resolve())
            self.assertEqual(config.base_dir, directory.resolve())

    def test_empty_log_file_means_no_file_logging(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = self._write(
                directory,
                """
                [app]
                log_file = ""

                [notifiers.console]
                enabled = true
                """,
            )
            config = load_config(path)
            self.assertIsNone(config.app.log_file)

    def test_environment_placeholder_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = self._write(
                directory,
                """
                [notifiers.console]
                enabled = true

                [notifiers.ntfy]
                enabled = true
                topic = "test-topic-123"
                token = "${TEST_NTFY_TOKEN}"
                """,
            )
            with patch.dict(os.environ, {"TEST_NTFY_TOKEN": "titok"}, clear=True):
                config = load_config(path)
            self.assertEqual(config.ntfy.token, "titok")

    def test_dotenv_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / ".env").write_text(
                "TEST_DOTENV_TOKEN=dotenv-titok\n",
                encoding="utf-8",
            )
            path = self._write(
                directory,
                """
                [notifiers.console]
                enabled = true

                [notifiers.ntfy]
                enabled = true
                topic = "test-topic-123"
                token = "${TEST_DOTENV_TOKEN}"
                """,
            )
            with patch.dict(os.environ, {}, clear=True):
                config = load_config(path)
            self.assertEqual(config.ntfy.token, "dotenv-titok")

    def test_real_environment_wins_over_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / ".env").write_text(
                "TEST_DOTENV_TOKEN=dotenv-titok\n",
                encoding="utf-8",
            )
            path = self._write(
                directory,
                """
                [notifiers.console]
                enabled = true

                [notifiers.ntfy]
                enabled = true
                topic = "test-topic-123"
                token = "${TEST_DOTENV_TOKEN}"
                """,
            )
            with patch.dict(os.environ, {"TEST_DOTENV_TOKEN": "env-titok"}, clear=True):
                config = load_config(path)
            self.assertEqual(config.ntfy.token, "env-titok")

    def test_requires_at_least_one_notifier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = self._write(
                directory,
                """
                [notifiers.console]
                enabled = false
                """,
            )
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_email_ssl_and_starttls_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = self._write(
                directory,
                """
                [notifiers.console]
                enabled = true

                [notifiers.email]
                enabled = true
                host = "smtp.example.com"
                ssl = true
                starttls = true
                from = "a@example.com"
                to = ["b@example.com"]
                """,
            )
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_invalid_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = directory / "config.toml"
            path.write_text("this is not toml [[[", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
