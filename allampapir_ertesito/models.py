"""Adatmodellek az AKK adatokhoz és az értesítésekhez."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .util import format_percent, format_rate_range


@dataclass(frozen=True)
class Offering:
    """Egy MÁP+ sorozat nyilvános ajánlattétele.

    Az AKK ``ehmString`` mezője a MÁP+ esetében a sávos kamatlábat tartalmazza
    (pl. "5,00 - 6,00"), ezért itt ``rate_text`` néven tároljuk.
    """

    name: str
    start_period: date
    end_period: date | None = None
    published: datetime | None = None
    maturity: date | None = None
    coupon: float | None = None
    rate_text: str | None = None
    ehm: float | None = None
    isin: str | None = None
    pdf_path: str | None = None
    label: str | None = None
    archive: bool = False
    modified_on: datetime | None = None

    @property
    def id(self) -> str:
        return f"{self.name}|{self.start_period.isoformat()}"

    @property
    def pdf_url(self) -> str | None:
        if not self.pdf_path:
            return None
        if self.pdf_path.startswith("http://") or self.pdf_path.startswith("https://"):
            return self.pdf_path
        return "https://documents.akk.hu/" + self.pdf_path.lstrip("/")

    @property
    def published_date(self) -> date | None:
        return self.published.date() if self.published else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "start_period": self.start_period.isoformat(),
            "end_period": self.end_period.isoformat() if self.end_period else None,
            "published": self.published.isoformat() if self.published else None,
            "maturity": self.maturity.isoformat() if self.maturity else None,
            "coupon": self.coupon,
            "rate_text": self.rate_text,
            "ehm": self.ehm,
            "isin": self.isin,
            "pdf_url": self.pdf_url,
            "label": self.label,
            "archive": self.archive,
        }


@dataclass(frozen=True)
class RetailSeries:
    """Az AKK 'Értékesítés alatt álló lakossági állampapírok kamata' adatsor egy sora."""

    name: str
    valid_from: date
    valid_to: date | None = None
    rate: str | None = None
    ehm: str | None = None
    maturity: date | None = None
    tenor: str | None = None
    row_type: str | None = None

    @property
    def id(self) -> str:
        return f"{self.name}|{self.valid_from.isoformat()}"

    def is_active(self, today: date) -> bool:
        return self.valid_from <= today and (self.valid_to is None or self.valid_to >= today)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "valid_from": self.valid_from.isoformat(),
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "rate": self.rate,
            "ehm": self.ehm,
            "maturity": self.maturity.isoformat() if self.maturity else None,
            "tenor": self.tenor,
            "type": self.row_type,
        }


@dataclass(frozen=True)
class SeriesInfo:
    """Értesítéshez összefésült sorozatinformáció (ajánlattétel + aktuális adat)."""

    name: str
    start: date
    end: date | None = None
    published: datetime | None = None
    maturity: date | None = None
    rate: str | None = None
    ehm: str | None = None
    isin: str | None = None
    pdf_url: str | None = None
    source: str = "offering"
    tenor: str | None = None

    @property
    def id(self) -> str:
        return self.name

    def matches(self, other_name: str) -> bool:
        from .util import series_name_key

        return series_name_key(self.name) == series_name_key(other_name)

    @classmethod
    def from_offering(
        cls,
        offering: Offering,
        retail: RetailSeries | None = None,
    ) -> "SeriesInfo":
        rate = None
        if retail and retail.rate:
            rate = retail.rate
        elif offering.rate_text:
            rate = offering.rate_text
        elif offering.coupon is not None:
            rate = f"{offering.coupon:g}"

        ehm = None
        if retail and retail.ehm:
            ehm = retail.ehm
        elif offering.ehm is not None:
            ehm = format_percent(offering.ehm)

        end = offering.end_period
        if end is None and retail:
            end = retail.valid_to

        maturity = offering.maturity or (retail.maturity if retail else None)
        tenor = retail.tenor if retail and retail.tenor else _infer_tenor(offering.start_period, maturity)

        return cls(
            name=offering.name,
            start=offering.start_period,
            end=end,
            published=offering.published,
            maturity=maturity,
            rate=rate,
            ehm=ehm,
            isin=offering.isin,
            pdf_url=offering.pdf_url,
            source="offering",
            tenor=tenor,
        )

    @classmethod
    def from_retail(cls, retail: RetailSeries) -> "SeriesInfo":
        return cls(
            name=retail.name,
            start=retail.valid_from,
            end=retail.valid_to,
            published=None,
            maturity=retail.maturity,
            rate=retail.rate,
            ehm=retail.ehm,
            isin=None,
            pdf_url=None,
            source="retail",
            tenor=retail.tenor,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "start": self.start.isoformat(),
            "end": self.end.isoformat() if self.end else None,
            "published": self.published.isoformat() if self.published else None,
            "maturity": self.maturity.isoformat() if self.maturity else None,
            "rate": self.rate,
            "rate_display": format_rate_range(self.rate),
            "ehm": self.ehm,
            "isin": self.isin,
            "pdf_url": self.pdf_url,
            "source": self.source,
            "tenor": self.tenor,
        }


def _infer_tenor(start: date, maturity: date | None) -> str | None:
    if maturity is None:
        return None
    years = round((maturity - start).days / 365.25)
    if years <= 0:
        return None
    return f"{years}Y"


@dataclass(frozen=True)
class Message:
    """Egy kimenő értesítés."""

    event: str
    title: str
    body: str
    series: SeriesInfo | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    image_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "title": self.title,
            "body": self.body,
            "series": self.series.to_dict() if self.series else None,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class CheckOutcome:
    """Egy ellenőrzési ciklus eredménye."""

    messages: list[Message] = field(default_factory=list)
    active: SeriesInfo | None = None
    upcoming: list[SeriesInfo] = field(default_factory=list)
    source_errors: list[str] = field(default_factory=list)
    delivery_failures: list[str] = field(default_factory=list)
    delivered_messages: int = 0
    dry_run: bool = False
    first_run: bool = False
