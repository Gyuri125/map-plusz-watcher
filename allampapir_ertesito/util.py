"""Kis segédfüggvények: szöveg-, dátum- és százalékformázás."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Any


def normalize_text(value: str) -> str:
    """Ékezet- és kisbetű-független összehasonlításhoz."""
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip().lower()


def is_map_plusz_type(value: str | None) -> bool:
    """Igaz, ha az AKK terméktípusa MÁP Plusz (és nem pl. nyomdai MÁP Plusz)."""
    if not value:
        return False
    normalized = normalize_text(value).replace("+", " plusz")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized in {"map plusz", "map plusz sorozat", "map plusz allampapir"}


def series_name_key(value: str) -> str:
    """Sorozatnevek összevetése (pl. N2030/M2 és 2030/M2)."""
    normalized = normalize_text(value).replace(" ", "")
    # A régebbi sorozatok N-előtagot kaptak, az újak nem.
    return re.sub(r"^n(?=\d{4}/)", "", normalized)


def parse_date(value: Any) -> date | None:
    """ISO dátum (YYYY-MM-DD) vagy datetime sztring parse-olása."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    # Az API néha időbélyeget is ad a dátum mezőben.
    text = text.replace("Z", "+00:00")
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def parse_datetime(value: Any) -> datetime | None:
    """Naív helyi időbélyeg parse-olása (az AKK európai időt használ)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        # "2026-09-25 13:30:00" formátumot a fromisoformat már kezeli,
        # de néhány rendszer "T" nélkül, tört másodperccel adja.
        try:
            return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


def to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("%", "").replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def format_percent(value: str | float | None, decimals: int = 2) -> str | None:
    """5.47 -> '5,47%', '5,00%' -> '5,00%'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().replace("%", "").replace(",", ".")
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    return f"{number:.{decimals}f}".replace(".", ",") + "%"


def format_rate_range(value: str | float | None) -> str | None:
    """'5.00 - 6.00' -> '5,00% – 6,00%'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return format_percent(value)
    text = str(value).strip()
    if not text:
        return None
    parts = [part for part in re.split(r"\s*[-–—]\s*", text) if part.strip()]
    formatted = [format_percent(part) for part in parts]
    formatted = [item for item in formatted if item]
    return " – ".join(formatted) if formatted else None


def format_date_hu(value: date | None, empty: str = "") -> str:
    if value is None:
        return empty
    return f"{value.year}. {value.month:02d}. {value.day:02d}."


def format_datetime_hu(value: datetime | None, empty: str = "") -> str:
    if value is None:
        return empty
    return f"{value.year}. {value.month:02d}. {value.day:02d}. {value.hour:02d}:{value.minute:02d}"


def format_datetime_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def truncate(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"
