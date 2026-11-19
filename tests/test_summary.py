from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from allampapir_ertesito.models import CheckOutcome, Message, SeriesInfo
from allampapir_ertesito.summary import build_summary, write_github_summary
from tests.helpers import make_config, make_offering, make_retail


class SummaryTests(unittest.TestCase):
    def _make_outcome(self) -> CheckOutcome:
        active_offering = make_offering(
            "2031/M6",
            date(2026, 10, 1),
            date(2026, 12, 31),
            published=datetime(2026, 9, 25, 13, 30),
        )
        upcoming_offering = make_offering(
            "2031/M7",
            date(2027, 1, 4),
            date(2027, 3, 31),
            published=datetime(2026, 12, 28, 13, 30),
        )
        active = SeriesInfo.from_offering(
            active_offering,
            make_retail("2031/M6", date(2026, 10, 1), None),
        )
        upcoming = SeriesInfo.from_offering(
            upcoming_offering,
            make_retail("2031/M7", date(2027, 1, 4), date(2027, 3, 31)),
        )
        return CheckOutcome(
            active=active,
            upcoming=[upcoming],
            messages=[Message(event="start", title="Már vásárolható: 2031/M6", body="x")],
        )

    def test_summary_contains_series_and_product_info(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            config.console.enabled = True
            text = build_summary(self._make_outcome(), config)
        self.assertIn("Jelenleg kapható", text)
        self.assertIn("2031/M6", text)
        self.assertIn("2031/M7", text)
        self.assertIn("Vételár", text)
        self.assertIn("5 éves", text)
        self.assertIn("console", text)

    def test_write_github_summary_uses_environment_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config = make_config(directory)
            config.console.enabled = True
            target = directory / "summary.md"
            with patch.dict(
                os.environ,
                {"GITHUB_STEP_SUMMARY": str(target)},
                clear=False,
            ):
                write_github_summary(self._make_outcome(), config)
            text = target.read_text(encoding="utf-8")
        self.assertIn("MÁP+ ellenőrzés", text)
        self.assertIn("2031/M6", text)


if __name__ == "__main__":
    unittest.main()
