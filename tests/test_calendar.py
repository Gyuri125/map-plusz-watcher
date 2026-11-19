from __future__ import annotations

import unittest
from datetime import date, datetime, timezone

from allampapir_ertesito.calendar import build_ics
from allampapir_ertesito.models import SeriesInfo
from tests.helpers import make_offering, make_retail


class CalendarTests(unittest.TestCase):
    def _series(self) -> SeriesInfo:
        offering = make_offering(
            "2031/M6",
            date(2026, 10, 1),
            date(2026, 12, 31),
            published=datetime(2026, 9, 25, 13, 30),
        )
        retail = make_retail("2031/M6", date(2026, 10, 1), None)
        return SeriesInfo.from_offering(offering, retail)

    def test_ics_contains_start_and_end_events(self) -> None:
        ics = build_ics(
            [self._series()],
            generated_at=datetime(2026, 11, 19, 13, 0, tzinfo=timezone.utc),
        )
        self.assertTrue(ics.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertTrue(ics.endswith("END:VCALENDAR\r\n"))
        self.assertIn("DTSTART;VALUE=DATE:20261001", ics)
        self.assertIn("DTEND;VALUE=DATE:20261002", ics)
        self.assertIn("DTSTART;VALUE=DATE:20261231", ics)
        self.assertIn("DTEND;VALUE=DATE:20270101", ics)
        self.assertIn("MÁP+ 2031/M6 – vásárlás kezdete", ics)
        self.assertIn("MÁP+ 2031/M6 – utolsó vásárlási nap", ics)
        self.assertIn("TRIGGER:-P1D", ics)
        self.assertIn("BEGIN:VEVENT", ics)
        self.assertEqual(ics.count("BEGIN:VEVENT"), 2)
        self.assertNotIn("..", ics)


if __name__ == "__main__":
    unittest.main()
