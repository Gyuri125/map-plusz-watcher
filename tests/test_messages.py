from __future__ import annotations

import unittest
from datetime import date, datetime

from allampapir_ertesito.messages import (
    build_announcement,
    build_ending_soon,
    build_first_run,
    build_start,
    build_status,
)
from allampapir_ertesito.models import SeriesInfo
from allampapir_ertesito.util import series_name_key
from tests.helpers import make_offering, make_retail


class MessageTests(unittest.TestCase):
    def _series(self, future: bool = False) -> SeriesInfo:
        if future:
            offering = make_offering(
                "2031/M7",
                date(2027, 1, 4),
                date(2027, 3, 31),
                published=datetime(2026, 12, 28, 13, 30),
            )
        else:
            offering = make_offering(
                "2031/M6",
                date(2026, 10, 1),
                date(2026, 12, 31),
                published=datetime(2026, 9, 25, 13, 30),
            )
        retail = make_retail(
            offering.name,
            offering.start_period,
            offering.end_period,
        )
        return SeriesInfo.from_offering(offering, retail)

    def test_announcement_contains_key_facts(self) -> None:
        message = build_announcement(self._series(future=True))
        self.assertIn("2031/M7", message.title)
        self.assertIn("2027. 01. 04.", message.body)
        self.assertIn("5,00% – 6,00%", message.body)
        self.assertIn("HU0000000001", message.body)
        self.assertIn("documents.akk.hu", message.body)
        self.assertIn("Fizetés:", message.body)
        self.assertIn("Kihirdetve:", message.body)
        self.assertIn("Termék:", message.body)
        self.assertIn("Vételár:", message.body)

    def test_start_on_start_day(self) -> None:
        message = build_start(self._series(), date(2026, 10, 1))
        self.assertIn("Ma válik vásárolhatóvá", message.title)
        self.assertIn("ma már megvásárolható", message.body)
        self.assertIn("Hátralévő idő: 91 nap", message.body)

    def test_ending_soon_contains_last_day_and_next_series(self) -> None:
        message = build_ending_soon(
            self._series(),
            date(2026, 12, 17),
            upcoming=self._series(future=True),
        )
        self.assertEqual(message.event, "ending")
        self.assertIn("2031/M6", message.title)
        self.assertIn("Utolsó vásárlási nap: 2026. 12. 31.", message.body)
        self.assertIn("2031/M7", message.body)
        self.assertIn("2027. 01. 04.", message.body)

    def test_announcement_has_countdown(self) -> None:
        message = build_announcement(self._series(future=True), date(2026, 12, 28))
        self.assertIn("Kezdésig: 7 nap", message.body)

    def test_status_message_lists_active_and_upcoming(self) -> None:
        message = build_status(
            self._series(),
            [self._series(future=True)],
            date(2026, 11, 19),
        )
        self.assertEqual(message.event, "status")
        self.assertIn("helyzetjelentés", message.title)
        self.assertIn("Jelenleg kapható", message.body)
        self.assertIn("Hamarosan indul", message.body)
        self.assertIn("2031/M6", message.body)
        self.assertIn("2031/M7", message.body)

    def test_first_run_lists_active_and_upcoming(self) -> None:
        active = self._series()
        upcoming = self._series(future=True)
        message = build_first_run(active, [upcoming])
        self.assertIn("Jelenleg kapható", message.body)
        self.assertIn("2031/M6", message.body)
        self.assertIn("Hamarosan indul", message.body)
        self.assertIn("2031/M7", message.body)
        self.assertEqual(series_name_key(message.series.name), "2031/m6")  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
