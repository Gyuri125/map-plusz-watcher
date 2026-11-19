from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

from allampapir_ertesito.dashboard import (
    DashboardData,
    _default_rate,
    _product_label,
    _select_products,
    render_html,
    write_dashboard,
)
from allampapir_ertesito.models import SeriesInfo
from tests.helpers import make_config, make_offering, make_retail


class DashboardTests(unittest.TestCase):
    def _data(self) -> DashboardData:
        m6_offering = make_offering(
            "2031/M6",
            date(2026, 10, 1),
            date(2026, 12, 31),
            published=datetime(2026, 9, 25, 13, 30),
        )
        m7_offering = make_offering(
            "2031/M7",
            date(2027, 1, 4),
            date(2027, 3, 31),
            published=datetime(2026, 12, 28, 13, 30),
        )
        active = SeriesInfo.from_offering(
            m6_offering,
            make_retail("2031/M6", date(2026, 10, 1), None),
        )
        upcoming = SeriesInfo.from_offering(
            m7_offering,
            make_retail("2031/M7", date(2027, 1, 4), date(2027, 3, 31)),
        )
        history = [
            make_retail("2031/M5", date(2026, 7, 17), date(2026, 9, 30)),
            make_retail("2031/M4", date(2026, 6, 15), date(2026, 7, 16)),
        ]
        products = [
            make_retail(
                "2031/M6",
                date(2026, 10, 1),
                None,
                rate="5.00 - 6.00",
                ehm="5.47",
            ),
            make_retail(
                "MAPP_F",
                date(2026, 10, 24),
                None,
                rate="4.50 - 5.75",
                ehm="5.23",
            ),
            make_retail(
                "2029/Q2",
                date(2026, 10, 1),
                None,
                rate="5.50",
                ehm="5.62",
            ),
            make_retail(
                "2045/S_BABA",
                date(2026, 2, 1),
                date(2027, 1, 31),
                rate="7.40",
                ehm=None,
            ),
        ]
        # A make_retail típusa fix, ezért a terméktípusokat itt igazítjuk.
        products = [
            replace(row, row_type=label)
            for row, label in zip(
                products,
                ["MÁP Plusz", "nyomdai MÁP Plusz", "FixMÁP", "BABA"],
            )
        ]
        return DashboardData(
            generated_at=datetime(2026, 11, 19, 13, 0, tzinfo=timezone.utc),
            active=active,
            upcoming=[upcoming],
            history=history,
            products=_select_products(products),
            pdf_by_name={"2031/M6": "https://documents.akk.hu/m6.pdf"},
            source_errors=[],
        )

    def test_product_filtering(self) -> None:
        data = self._data()
        selected = _select_products(data.products)
        labels = [_product_label(row.row_type) for row in selected]
        self.assertEqual(labels, ["MÁP+", "FixMÁP"])
        self.assertEqual(selected[0].name, "2031/M6")

    def test_default_rate(self) -> None:
        self.assertEqual(_default_rate(self._data()), 5.0)

    def test_render_html_contains_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            html = render_html(self._data(), config)
        for text in [
            "2031/M6",
            "Hamarosan indul",
            "EHM alakulása",
            "Korábbi sorozatok",
            "MÁP+ és más állampapírok",
            "Hozamkalkulátor",
            "Naptárba (.ics)",
            "map-plusz.ics",
            "FixMÁP",
        ]:
            self.assertIn(text, html)
        self.assertNotIn("Nyomdai MÁP+", html)
        self.assertNotIn("BABA", html)

    def test_render_without_calculator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            html = render_html(self._data(), config, show_calculator=False)
        self.assertNotIn("Hozamkalkulátor", html)
        self.assertNotIn('id="kalkulator"', html)

    def test_write_dashboard_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config = make_config(directory)
            output = directory / "site"
            index = write_dashboard(self._data(), config, output)
            self.assertTrue(index.exists())
            self.assertTrue((output / "map-plusz.ics").exists())
            self.assertTrue((output / "data.json").exists())
            self.assertIn("BEGIN:VCALENDAR", (output / "map-plusz.ics").read_text(encoding="utf-8"))
            self.assertIn("2031/M6", (output / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
