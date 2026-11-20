from __future__ import annotations

import importlib.util
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

from allampapir_ertesito.dashboard import DashboardData
from allampapir_ertesito.models import SeriesInfo
from tests.helpers import make_offering, make_retail

HAS_PILLOW = importlib.util.find_spec("PIL") is not None


@unittest.skipUnless(HAS_PILLOW, "A Pillow nincs telepítve")
class ChartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)

    def _data(self) -> DashboardData:
        offering = make_offering(
            "2031/M6",
            date(2026, 10, 1),
            date(2026, 12, 31),
            published=datetime(2026, 9, 25, 13, 30),
        )
        retail = make_retail("2031/M6", date(2026, 10, 1), None)
        active = SeriesInfo.from_offering(offering, retail)
        history = [
            make_retail("2031/M4", date(2026, 6, 15), None, rate="5.50 - 6.50", ehm="5.99"),
            make_retail("2031/M5", date(2026, 7, 17), None, rate="5.00 - 6.00", ehm="5.48"),
            make_retail("2031/M6", date(2026, 10, 1), None, rate="5.00 - 6.00", ehm="5.47"),
        ]
        products = [
            replace(retail, name="2031/M6", row_type="MÁP Plusz"),
            replace(retail, name="2029/Q2", row_type="FixMÁP", rate="5,50%", ehm="5,62%"),
            replace(retail, name="2028/L", row_type="PMÁP", rate="4,65%", ehm=None),
            replace(retail, name="2029/N", row_type="BMÁP", rate="6,67%", ehm=None),
        ]
        return DashboardData(
            generated_at=datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc),
            active=active,
            upcoming=[],
            history=history,
            products=products,
            pdf_by_name={},
            source_errors=[],
        )

    def test_renders_png_with_history_and_products(self) -> None:
        from allampapir_ertesito.chart import render_chart

        path = render_chart(self._data(), self.directory / "chart.png")
        self.assertTrue(path.is_file())
        self.assertGreater(path.stat().st_size, 5000)
        self.assertEqual(path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_renders_empty_data_without_error(self) -> None:
        from allampapir_ertesito.chart import render_chart

        data = DashboardData(
            generated_at=datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc),
            active=None,
            upcoming=[],
            history=[],
            products=[],
            pdf_by_name={},
            source_errors=[],
        )
        path = render_chart(data, self.directory / "empty.png")
        self.assertTrue(path.is_file())


if __name__ == "__main__":
    unittest.main()
