from __future__ import annotations

import unittest
from datetime import date

from allampapir_ertesito.util import (
    format_date_hu,
    format_percent,
    format_rate_range,
    is_map_plusz_type,
    series_name_key,
)


class UtilTests(unittest.TestCase):
    def test_percent_formatting(self) -> None:
        self.assertEqual(format_percent("5.47"), "5,47%")
        self.assertEqual(format_percent(5), "5,00%")
        self.assertEqual(format_rate_range("5.00 - 6.00"), "5,00% – 6,00%")
        self.assertEqual(format_rate_range("5,75 - 6,75"), "5,75% – 6,75%")
        self.assertEqual(format_rate_range("5.0"), "5,00%")

    def test_date_formatting(self) -> None:
        self.assertEqual(format_date_hu(date(2026, 10, 1)), "2026. 10. 01.")
        self.assertEqual(format_date_hu(None), "")

    def test_map_plusz_type(self) -> None:
        self.assertTrue(is_map_plusz_type("MÁP Plusz"))
        self.assertTrue(is_map_plusz_type("MÁP+"))
        self.assertFalse(is_map_plusz_type("nyomdai MÁP Plusz"))
        self.assertFalse(is_map_plusz_type("FixMÁP"))

    def test_series_name_key_handles_n_prefix(self) -> None:
        self.assertEqual(series_name_key("N2030/M2"), series_name_key("2030/M2"))
        self.assertEqual(series_name_key("2031/M6"), "2031/m6")


if __name__ == "__main__":
    unittest.main()
