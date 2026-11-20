"""Magyar nyelvű értesítésszövegek készítése."""

from __future__ import annotations

from datetime import date

from .models import Message, SeriesInfo
from .util import (
    format_date_hu,
    format_datetime_hu,
    format_percent,
    format_rate_range,
)

PRODUCT_PAGE = (
    "https://www.akk.hu/hu/allampapir-forgalmazas/allampapir-tipusok/"
    "magyar-allampapir-plusz-map-plusz"
)
OFFERING_PAGE = (
    "https://www.akk.hu/hu/allampapir-forgalmazas/nyilvanos-ajanlattetelek/"
    "mapp_t-hu-po"
)
WEBKINCSTAR_URL = "https://webkincstar.allamkincstar.gov.hu/"
TREASURY_URL = "https://www.allamkincstar.gov.hu/"

PAYMENT_NOTE = (
    "Fizetés: a vételárat a vásárlásnál kell rendezni. WebKincstárnál ehhez "
    "elegendő pénznek kell lennie a pénzszámládon; bankfiókban vagy MÁK "
    "irodában a helyszínen fizetsz. A forgalmazási díj forgalmazónként eltérhet."
)

PRODUCT_FEATURES = (
    "5 éves futamidő, fix sávos kamatozás, 1 Ft-os alapcímlet; "
    "a kamat évente kerül jóváírásra."
)

PURCHASE_PRICE_NOTE = (
    "a névérték 100%-a + a vásárlásig felhalmozott kamat, valamint a "
    "forgalmazó díja (ha van)"
)


def _date_range(series: SeriesInfo) -> str:
    start = format_date_hu(series.start)
    if series.end is None:
        return f"{start} – visszavonásig"
    return f"{start} – {format_date_hu(series.end)}"


def _days_left(target: date, today: date) -> str:
    days = (target - today).days
    if days == 0:
        return "ma"
    if days == 1:
        return "1 nap"
    return f"{days} nap"


def _series_details(
    series: SeriesInfo,
    *,
    include_isin: bool = True,
    include_published: bool = False,
    today: date | None = None,
) -> list[str]:
    lines = [
        f"  Sorozat: {series.name}",
    ]
    if include_isin and series.isin:
        lines.append(f"  ISIN: {series.isin}")
    if include_published and series.published:
        lines.append(f"  Kihirdetve: {format_datetime_hu(series.published)}")
    lines.append(f"  Értékesítés: {_date_range(series)}")
    if today is not None:
        if series.start > today:
            lines.append(f"  Kezdésig: {_days_left(series.start, today)}")
        elif series.end is not None and series.end >= today:
            lines.append(f"  Hátralévő idő: {_days_left(series.end, today)}")
    if series.maturity:
        lines.append(f"  Lejárat: {format_date_hu(series.maturity)}")
    rate = format_rate_range(series.rate)
    if rate:
        lines.append(f"  Kamat: {rate}")
    if series.ehm:
        ehm = format_percent(series.ehm)
        if ehm:
            lines.append(f"  EHM: {ehm}")
    lines.append(f"  Termék: {PRODUCT_FEATURES}")
    lines.append(f"  Vételár: {PURCHASE_PRICE_NOTE}.")
    return lines


def _purchase_lines() -> list[str]:
    return [
        "Vásárlás:",
        f"  WebKincstár: {WEBKINCSTAR_URL}",
        f"  Magyar Államkincstár irodái: {TREASURY_URL}",
        "  Lakossági forgalmazók (bankok)",
    ]


def _info_lines(series: SeriesInfo) -> list[str]:
    lines = ["További információ:"]
    if series.pdf_url:
        lines.append(f"  Nyilvános ajánlattétel (PDF): {series.pdf_url}")
    lines.append(f"  MÁP+ termékoldal: {PRODUCT_PAGE}")
    lines.append(f"  Nyilvános ajánlattételek: {OFFERING_PAGE}")
    return lines


def _disclaimer() -> str:
    return (
        "Ez az értesítés nem befektetési tanács. Vásárlás előtt ellenőrizd a "
        "hivatalos dokumentumokat az ÁKK oldalán."
    )


def build_announcement(series: SeriesInfo, today: date | None = None) -> Message:
    title = f"Új MÁP+ sorozat érkezik: {series.name}"
    lines = [
        "Az ÁKK kihirdette a következő MÁP+ sorozatot.",
        "",
        *_series_details(
            series,
            include_published=True,
            today=today,
        ),
        "",
        "A sorozat a fenti kezdőnaptól vásárolható a WebKincstárban, a Magyar "
        "Államkincstár irodáiban és a lakossági forgalmazóknál.",
        "",
        PAYMENT_NOTE,
        "",
        *_purchase_lines(),
        "",
        *_info_lines(series),
        "",
        _disclaimer(),
    ]
    return Message(event="announcement", title=title, body="\n".join(lines), series=series)


def build_start(series: SeriesInfo, today: date) -> Message:
    if series.start == today:
        title = f"Ma válik vásárolhatóvá: {series.name} MÁP+"
        intro = f"A(z) {series.name} MÁP+ sorozat ma már megvásárolható."
    else:
        title = f"Már vásárolható: {series.name} MÁP+"
        intro = (
            f"A(z) {series.name} MÁP+ sorozat már vásárolható "
            f"({format_date_hu(series.start)} óta)."
        )
    lines = [
        intro,
        "",
        *_series_details(series, today=today),
        "",
        PAYMENT_NOTE,
        "",
        *_purchase_lines(),
        "",
        *_info_lines(series),
        "",
        _disclaimer(),
    ]
    return Message(event="start", title=title, body="\n".join(lines), series=series)


def build_ending_soon(
    series: SeriesInfo,
    today: date,
    upcoming: SeriesInfo | None = None,
    last_day: bool = False,
) -> Message:
    end_text = format_date_hu(series.end) if series.end else "hamarosan"
    if last_day:
        title = f"Utolsó vásárlási nap: {series.name} MÁP+"
        intro = (
            f"Ma van az utolsó nap, amikor a(z) {series.name} MÁP+ sorozat "
            "még megvásárolható."
        )
    else:
        days = (series.end - today).days if series.end else 0
        title = f"Hamarosan véget ér: {series.name} MÁP+"
        intro = (
            f"A(z) {series.name} MÁP+ sorozat értékesítése hamarosan véget ér. "
            f"Utolsó vásárlási nap: {end_text} ({days} nap múlva)."
        )

    lines = [intro, "", *_series_details(series, today=today), ""]
    if upcoming is not None:
        lines.append("Következő sorozat:")
        lines.extend(
            _series_details(
                upcoming,
                include_published=True,
                today=today,
            )
        )
        if not format_rate_range(upcoming.rate):
            lines.append("  A következő sorozat kamata még nem ismert.")
        lines.extend(
            [
                "",
                "Ha a jelenlegi sorozat kamata jobb, az utolsó vásárlási napig "
                "még megvásárolható. Döntés előtt hasonlítsd össze a hivatalos "
                "kamat- és EHM-adatokat.",
            ]
        )
        lines.append("")

    lines.extend(
        [
            PAYMENT_NOTE,
            "",
            *_purchase_lines(),
            "",
            *_info_lines(series),
            "",
            _disclaimer(),
        ]
    )
    return Message(event="ending", title=title, body="\n".join(lines), series=series)


def build_first_run(
    active: SeriesInfo | None,
    upcoming: list[SeriesInfo],
    today: date | None = None,
) -> Message:
    title = "MÁP+ értesítő elindult"
    lines = [
        "A MÁP+ értesítő elindult.",
        "",
        "Mostantól értesítést küldök, amikor az ÁKK új MÁP+ sorozatot hirdet "
        "meg, amikor egy sorozat megvásárolhatóvá válik, és amikor a "
        "jelenlegi sorozat utolsó vásárlási napja közeledik.",
        "",
    ]
    if active:
        lines.append("Jelenleg kapható:")
        lines.extend(_series_details(active, today=today))
        lines.append("")
    else:
        lines.append("Jelenleg nincs forgalmazás alatt álló MÁP+ sorozat.")
        lines.append("")

    if upcoming:
        lines.append("Hamarosan indul:")
        for series in upcoming:
            lines.extend(
                _series_details(
                    series,
                    include_published=True,
                    today=today,
                )
            )
            lines.append("")

    if active:
        lines.append(PAYMENT_NOTE)
        lines.append("")

    lines.extend(
        [
            "Ez az első összefoglaló. A következő értesítés új sorozat "
            "kihirdetésekor, indulásakor vagy a vásárlási időszak végéhez "
            "közeledve jön.",
        ]
    )
    series_for_message = active or (upcoming[0] if upcoming else None)
    return Message(
        event="first_run",
        title=title,
        body="\n".join(lines),
        series=series_for_message,
    )


def build_status(
    active: SeriesInfo | None,
    upcoming: list[SeriesInfo],
    today: date | None = None,
) -> Message:
    date_part = f" – {format_date_hu(today).rstrip('.')}" if today else ""
    title = f"MÁP+ helyzetjelentés{date_part}"
    lines = ["Aktuális MÁP+ helyzet.", ""]
    if active:
        lines.append("Jelenleg kapható:")
        lines.extend(_series_details(active, today=today))
        lines.append("")
    else:
        lines.append("Jelenleg nincs forgalmazás alatt álló MÁP+ sorozat.")
        lines.append("")

    if upcoming:
        lines.append("Hamarosan indul:")
        for series in upcoming:
            lines.extend(
                _series_details(
                    series,
                    include_published=True,
                    today=today,
                )
            )
            lines.append("")
    else:
        lines.append("Nincs kihirdetett következő sorozat a figyelt időszakban.")
        lines.append("")

    if active:
        lines.append(PAYMENT_NOTE)
        lines.append("")
    lines.extend(_purchase_lines())
    lines.append("")
    series_for_message = active or (upcoming[0] if upcoming else None)
    if series_for_message is not None:
        lines.extend(_info_lines(series_for_message))
    else:
        lines.append(f"MÁP+ termékoldal: {PRODUCT_PAGE}")
    lines.append("")
    lines.append(_disclaimer())
    return Message(
        event="status",
        title=title,
        body="\n".join(lines).strip(),
        series=series_for_message,
    )


def build_reminder(
    series: SeriesInfo,
    reminder_text: str,
    today: date | None = None,
) -> Message:
    title = f"Vásárlási emlékeztető: {series.name} MÁP+"
    lines = [
        reminder_text.strip(),
        "",
        *_series_details(
            series,
            include_isin=False,
            today=today,
        ),
        "",
        PAYMENT_NOTE,
        "",
        *_purchase_lines(),
        "",
        "Ha már megvásároltad a sorozatot, tekintsd tárgytalannak ezt az "
        "emlékeztetőt.",
    ]
    return Message(event="reminder", title=title, body="\n".join(lines), series=series)


def build_test() -> Message:
    lines = [
        "Ez egy tesztértesítés a MÁP+ értesítőtől.",
        "",
        "Ha ezt látod, az értesítési csatorna működik.",
        "",
        "A figyelő a következő ellenőrzéskor valós adatokat keres az ÁKK "
        "nyilvános adatforrásaiban, és csak új sorozat, indulás vagy a "
        "vásárlási időszak vége előtt küld értesítést.",
        "",
        f"MÁP+ termékoldal: {PRODUCT_PAGE}",
    ]
    return Message(event="test", title="MÁP+ értesítő – teszt", body="\n".join(lines))


def build_error(error: str) -> Message:
    lines = [
        "Nem sikerült lekérni az ÁKK adatait.",
        "",
        f"Hiba: {error}",
        "",
        "A figyelő a következő alkalommal újra próbálkozik. Ha a hiba "
        "tartósan fennáll, ellenőrizd az internetkapcsolatot, illetve azt, "
        "hogy az ÁKK nem változtatta-e meg az API-t.",
        "",
        f"Adatforrás: {OFFERING_PAGE}",
    ]
    return Message(event="error", title="MÁP+ értesítő – adatlekérési hiba", body="\n".join(lines))
