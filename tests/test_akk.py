from __future__ import annotations

import unittest
from datetime import date, datetime

from allampapir_ertesito.akk import dedupe_offerings, parse_offerings, parse_retail
from allampapir_ertesito.monitor import match_retail
from tests.helpers import make_offering, make_retail


class AkkParsingTests(unittest.TestCase):
    def test_parse_offerings_and_dedupe_amendment(self) -> None:
        rows = [
            {
                "name": "2031/M7",
                "startPeriod": "2027-01-04",
                "endPeriod": "2027-03-31",
                "published": "2026-12-28 13:30:00",
                "maturity": "2032-01-04",
                "coupon": 5.0,
                "ehmString": "5,00 - 6,00",
                "isin": "HU0000409999",
                "path": "public_offerings/a.pdf",
                "label": "MÁPP_T",
                "archive": False,
            },
            {
                "name": "2031/M7",
                "startPeriod": "2027-01-04",
                "endPeriod": "2027-03-31",
                "published": "2027-01-02 10:00:00",
                "maturity": "2032-01-04",
                "coupon": 5.5,
                "ehmString": "5,50 - 6,50",
                "isin": "HU0000409999",
                "path": "public_offerings/b.pdf",
                "label": "MÁPP_T",
                "archive": False,
            },
        ]
        result = parse_offerings(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].coupon, 5.5)
        self.assertEqual(result[0].rate_text, "5,50 - 6,50")
        self.assertEqual(result[0].pdf_url, "https://documents.akk.hu/public_offerings/b.pdf")
        self.assertEqual(result[0].published, datetime(2027, 1, 2, 10, 0))

    def test_parse_offerings_skips_invalid_rows(self) -> None:
        rows = [
            {"name": "", "startPeriod": "2027-01-04"},
            {"name": "2031/M7", "startPeriod": None},
            {"name": "2031/M8", "startPeriod": "2027-02-01"},
        ]
        result = parse_offerings(rows)
        self.assertEqual([item.name for item in result], ["2031/M8"])

    def test_dedupe_keeps_latest_publication(self) -> None:
        first = make_offering("2031/M7", date(2027, 1, 4), date(2027, 3, 31))
        second = make_offering(
            "2031/M7",
            date(2027, 1, 4),
            date(2027, 3, 31),
            published=datetime(2027, 1, 2, 10, 0),
        )
        result = dedupe_offerings([first, second])
        self.assertEqual(result, [second])

    def test_parse_retail(self) -> None:
        rows = [
            {
                "name": "2031/M6",
                "validFrom": "2026-10-01",
                "validTo": None,
                "rate": "5.00 - 6.00",
                "ehm": "5.47",
                "maturity": "2031-11-27",
                "tenor": "5Y",
                "type": "MÁP Plusz",
            },
            {
                "name": "2031/M5",
                "validFrom": "2026-07-17",
                "validTo": "2026-09-30",
                "rate": "5.00 - 6.00",
                "ehm": "5.48",
                "maturity": "2031-08-21",
                "tenor": "5Y",
                "type": "MÁP Plusz",
            },
        ]
        result = parse_retail(rows)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "2031/M5")
        self.assertEqual(result[1].name, "2031/M6")
        self.assertIsNone(result[1].valid_to)

    def test_match_retail_with_n_prefix(self) -> None:
        offering = make_offering("2030/M2", date(2025, 2, 3), date(2025, 2, 28))
        retail_rows = [
            make_retail("N2030/M2", date(2025, 2, 3), date(2025, 2, 28)),
            make_retail("N2030/M1", date(2025, 1, 2), date(2025, 1, 31)),
        ]
        matched = match_retail(offering, retail_rows, date(2025, 2, 10))
        self.assertIsNotNone(matched)
        assert matched is not None
        self.assertEqual(matched.name, "N2030/M2")


if __name__ == "__main__":
    unittest.main()
