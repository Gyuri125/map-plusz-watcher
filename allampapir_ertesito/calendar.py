"""Naptárfájl (.ics) generálása a dashboardhoz."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from .models import SeriesInfo
from .util import format_date_hu, format_percent, format_rate_range

PUBLIC_URL = "https://gyuri125.github.io/map-plusz-watcher/"


def _escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """RFC 5545 szerinti 75 oktetes tördelés."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    parts: list[str] = []
    current = ""
    for char in line:
        candidate = current + char
        if len(candidate.encode("utf-8")) > 73:
            parts.append(current)
            current = char
        else:
            current = candidate
    if current:
        parts.append(current)
    return "\r\n ".join(parts)


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()


def _date(value: date) -> str:
    return format_date_hu(value).rstrip(".")


def _event(
    series: SeriesInfo,
    *,
    event_date: date,
    summary: str,
    stamp: str,
    page_url: str,
) -> list[str]:
    end_date = event_date + timedelta(days=1)
    rate = format_rate_range(series.rate) or "–"
    ehm = format_percent(series.ehm) or "–"
    start_text = _date(series.start)
    end_text = _date(series.end) if series.end else "visszavonásig"
    maturity_text = _date(series.maturity) if series.maturity else "–"
    description = (
        f"MÁP+ {series.name}. Kamat: {rate}. EHM: {ehm}. "
        f"Értékesítés: {start_text} – {end_text}. "
        f"Lejárat: {maturity_text}. "
        f"WebKincstár: https://webkincstar.allamkincstar.gov.hu/"
    )
    uid = f"{_slug(series.name)}-{event_date.strftime('%Y%m%d')}@map-plusz-watcher"
    url = series.pdf_url or page_url
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{event_date.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{end_date.strftime('%Y%m%d')}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(description)}",
    ]
    if url:
        lines.append(f"URL:{url}")
    lines.extend(
        [
            "STATUS:CONFIRMED",
            "TRANSP:TRANSPARENT",
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_escape(summary)}",
            "TRIGGER:-P1D",
            "END:VALARM",
            "END:VEVENT",
        ]
    )
    return lines


def build_ics(
    series_list: list[SeriesInfo],
    *,
    generated_at: datetime | None = None,
    page_url: str = PUBLIC_URL,
) -> str:
    stamp = (generated_at or datetime.now(timezone.utc)).astimezone(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MAP Plusz Watcher//HU",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:MÁP+ Watcher",
        "X-WR-CALDESC:MÁP+ sorozatok indulása és utolsó vásárlási napja",
    ]
    for series in series_list:
        lines.extend(
            _event(
                series,
                event_date=series.start,
                summary=f"MÁP+ {series.name} – vásárlás kezdete",
                stamp=stamp,
                page_url=page_url,
            )
        )
        if series.end is not None:
            lines.extend(
                _event(
                    series,
                    event_date=series.end,
                    summary=f"MÁP+ {series.name} – utolsó vásárlási nap",
                    stamp=stamp,
                    page_url=page_url,
                )
            )
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
