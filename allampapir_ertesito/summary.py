"""GitHub Actions futtatási összefoglaló (Step Summary)."""

from __future__ import annotations

import logging
import os

from .config import Config
from .messages import PRODUCT_FEATURES, PURCHASE_PRICE_NOTE
from .models import CheckOutcome, SeriesInfo
from .util import format_date_hu, format_percent, format_rate_range

logger = logging.getLogger("allampapir.summary")


def _table_row(series: SeriesInfo) -> str:
    rate = format_rate_range(series.rate) or "–"
    ehm = format_percent(series.ehm) or "–"
    end = format_date_hu(series.end) if series.end else "visszavonásig"
    maturity = format_date_hu(series.maturity) if series.maturity else "–"
    return (
        f"| **{series.name}** | {rate} | {ehm} | "
        f"{format_date_hu(series.start)} – {end} | {maturity} |"
    )


def build_summary(outcome: CheckOutcome, config: Config) -> str:
    lines: list[str] = [
        "## MÁP+ ellenőrzés",
        "",
        f"Csatornák: `{', '.join(config.enabled_notifier_names)}`",
        "",
    ]

    if outcome.active is not None:
        lines.extend(
            [
                "### Jelenleg kapható",
                "",
                "| Sorozat | Kamat | EHM | Értékesítés | Lejárat |",
                "|---|---|---|---|---|",
                _table_row(outcome.active),
                "",
                f"**Vételár:** {PURCHASE_PRICE_NOTE}.",
                "",
                f"**Termék:** {PRODUCT_FEATURES}",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "### Jelenleg kapható",
                "",
                "Jelenleg nincs forgalmazás alatt álló MÁP+ sorozat.",
                "",
            ]
        )

    if outcome.upcoming:
        lines.extend(
            [
                "### Hamarosan indul",
                "",
                "| Sorozat | Kamat | EHM | Értékesítés | Lejárat |",
                "|---|---|---|---|---|",
                *[_table_row(series) for series in outcome.upcoming],
                "",
            ]
        )
    else:
        lines.extend(
            [
                "### Hamarosan indul",
                "",
                "Nincs kihirdetett következő sorozat a figyelt időszakban.",
                "",
            ]
        )

    if outcome.messages:
        lines.extend(
            [
                "### Értesítések",
                "",
                *[f"- {message.title}" for message in outcome.messages],
                "",
            ]
        )
    else:
        lines.extend(["### Értesítések", "", "Nincs új értesítés.", ""])

    if outcome.source_errors:
        lines.extend(
            [
                "### Adatforrás hibák",
                "",
                *[f"- {error}" for error in outcome.source_errors],
                "",
            ]
        )
    if outcome.delivery_failures:
        lines.extend(
            [
                "### Kézbesítési hibák",
                "",
                *[f"- {error}" for error in outcome.delivery_failures],
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def write_github_summary(outcome: CheckOutcome, config: Config) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(build_summary(outcome, config))
    except OSError as exc:
        logger.warning("A GitHub Actions összefoglaló nem írható: %s", exc)
