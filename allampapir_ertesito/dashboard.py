"""Statikus GitHub Pages dashboard és naptárfájl generálása."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .akk import AkkClient, AkkError
from .calendar import build_ics
from .config import Config
from .messages import (
    OFFERING_PAGE,
    PRODUCT_PAGE,
    PURCHASE_PRICE_NOTE,
    WEBKINCSTAR_URL,
)
from .models import Offering, RetailSeries, SeriesInfo
from .monitor import (
    SystemClock,
    latest_active_retail,
    match_retail,
    merge_series,
    select_active_offerings,
    select_future_offerings,
)
from .util import (
    format_date_hu,
    format_datetime_hu,
    format_percent,
    format_rate_range,
    is_map_plusz_type,
    normalize_text,
    series_name_key,
    to_float,
)

GITHUB_URL = "https://github.com/Gyuri125/map-plusz-watcher"


class DashboardError(RuntimeError):
    """A dashboardhoz nem sikerült adatot szerezni."""


@dataclass
class DashboardData:
    generated_at: datetime
    active: SeriesInfo | None
    upcoming: list[SeriesInfo]
    history: list[RetailSeries]
    products: list[RetailSeries]
    pdf_by_name: dict[str, str]
    source_errors: list[str]


def _product_label(row_type: str | None) -> str:
    value = normalize_text(row_type or "")
    if "nyomdai" in value:
        return "Nyomdai MÁP+"
    if "map plusz" in value:
        return "MÁP+"
    if "fixmap" in value:
        return "FixMÁP"
    if "pmap" in value or "premium" in value:
        return "PMÁP"
    if "bmap" in value or "bonusz" in value:
        return "BMÁP"
    if "1map" in value or "egy eves" in value:
        return "1MÁP"
    if "2map" in value or "ket eves" in value:
        return "2MÁP"
    if "baba" in value:
        return "Baba"
    if "emap" in value or "euro" in value:
        return "EMÁP"
    if "ktj" in value:
        return "KTJ"
    return (row_type or "Egyéb").strip() or "Egyéb"


_PRODUCT_ORDER = {
    "MÁP+": 0,
    "FixMÁP": 1,
    "PMÁP": 2,
    "BMÁP": 3,
    "1MÁP": 4,
    "2MÁP": 5,
    "EMÁP": 6,
    "Baba": 7,
    "KTJ": 8,
}


def _select_products(products: list[RetailSeries]) -> list[RetailSeries]:
    allowed = {"MÁP+", "FixMÁP", "PMÁP", "BMÁP", "1MÁP", "2MÁP"}
    best: dict[str, RetailSeries] = {}
    for row in products:
        label = _product_label(row.row_type)
        if label not in allowed:
            continue
        current = best.get(label)
        if current is None:
            best[label] = row
            continue
        current_ehm = to_float(current.ehm) or -1.0
        row_ehm = to_float(row.ehm) or -1.0
        if (row.valid_from, row_ehm) > (current.valid_from, current_ehm):
            best[label] = row
    return sorted(
        best.values(),
        key=lambda item: (
            _PRODUCT_ORDER.get(_product_label(item.row_type), 9),
            item.name,
        ),
    )


def _dedupe_history(rows: list[RetailSeries], active_name: str | None) -> list[RetailSeries]:
    unique: dict[str, RetailSeries] = {}
    for row in rows:
        if not is_map_plusz_type(row.row_type):
            continue
        if active_name and series_name_key(row.name) == series_name_key(active_name):
            continue
        current = unique.get(series_name_key(row.name))
        if current is None or row.valid_from > current.valid_from:
            unique[series_name_key(row.name)] = row
    return sorted(unique.values(), key=lambda item: item.valid_from, reverse=True)[:12]


def build_data(client: AkkClient, config: Config) -> DashboardData:
    clock = SystemClock(config.app.timezone)
    now = clock.now()
    today = now.date()
    now_naive = now.replace(tzinfo=None) if now.tzinfo else now

    offerings: list[Offering] = []
    retail_map: list[RetailSeries] = []
    products: list[RetailSeries] = []
    errors: list[str] = []

    try:
        offerings = client.fetch_offerings(
            today,
            lookback_days=config.app.lookback_days,
            horizon_days=config.app.announce_horizon_days,
        )
    except AkkError as exc:
        errors.append(f"ajánlattételek: {exc}")

    try:
        retail_map = client.fetch_retail(
            today,
            lookback_days=config.app.lookback_days,
        )
    except AkkError as exc:
        errors.append(f"MÁP+ kamatok: {exc}")

    try:
        products = client.fetch_retail_products(today)
    except AkkError as exc:
        errors.append(f"összehasonlítás: {exc}")

    if not offerings and not retail_map and not products:
        raise DashboardError("; ".join(errors) or "Nincs elérhető adat.")

    active_offerings = select_active_offerings(offerings, today, now_naive)
    future_offerings = select_future_offerings(
        offerings,
        today,
        config.app.announce_horizon_days,
        now_naive,
    )
    active_views = [
        merge_series(offering, match_retail(offering, retail_map, today))
        for offering in active_offerings
    ]
    future_views = [
        merge_series(offering, match_retail(offering, retail_map, today))
        for offering in future_offerings
    ]

    active: SeriesInfo | None = None
    if active_views:
        active = max(active_views, key=lambda item: (item.start, item.name))
    else:
        retail_active = latest_active_retail(retail_map, today)
        if retail_active is not None:
            active = SeriesInfo.from_retail(retail_active)

    pdf_by_name: dict[str, str] = {}
    for offering in offerings:
        if offering.pdf_url:
            pdf_by_name[offering.name] = offering.pdf_url
            pdf_by_name[series_name_key(offering.name)] = offering.pdf_url

    history = _dedupe_history(retail_map, active.name if active else None)
    selected_products = _select_products(products)

    return DashboardData(
        generated_at=now,
        active=active,
        upcoming=future_views,
        history=history,
        products=selected_products,
        pdf_by_name=pdf_by_name,
        source_errors=errors,
    )


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _date_range(series: SeriesInfo) -> str:
    end = format_date_hu(series.end) if series.end else "visszavonásig"
    return f"{format_date_hu(series.start)} – {end}"


def _days_text(target: date, today: date) -> str:
    days = (target - today).days
    if days == 0:
        return "ma"
    if days == 1:
        return "1 nap"
    return f"{days} nap"


def _countdown(series: SeriesInfo, today: date) -> str | None:
    if series.start > today:
        return f"Kezdésig: {_days_text(series.start, today)}"
    if series.end is not None and series.end >= today:
        return f"Hátralévő idő: {_days_text(series.end, today)}"
    return None


def _metric(label: str, value: str) -> str:
    return (
        '<div class="metric">'
        f'<div class="label">{_e(label)}</div>'
        f'<div class="value">{_e(value)}</div>'
        "</div>"
    )


def _series_actions(series: SeriesInfo | None, *, include_calendar: bool = True) -> str:
    links = [
        f'<a class="btn primary" href="{_e(WEBKINCSTAR_URL)}" target="_blank" rel="noopener">WebKincstár</a>'
    ]
    if series and series.pdf_url:
        links.append(
            f'<a class="btn" href="{_e(series.pdf_url)}" target="_blank" rel="noopener">Ajánlattétel</a>'
        )
    if include_calendar:
        links.append('<a class="btn blue" href="map-plusz.ics">Naptárba (.ics)</a>')
    links.append(
        f'<a class="btn" href="{_e(PRODUCT_PAGE)}" target="_blank" rel="noopener">AKK termékoldal</a>'
    )
    return '<div class="actions">' + "".join(links) + "</div>"


def _hero(data: DashboardData, today: date) -> str:
    if data.active is None:
        return (
            '<div class="card hero-card">'
            '<p class="eyebrow">Jelenleg kapható</p>'
            "<h1>Nincs aktív MÁP+ sorozat</h1>"
            '<p class="lead">Jelenleg nincs forgalmazás alatt álló MÁP+ sorozat. '
            "A következő indulásról értesítést küldünk.</p>"
            f"{_series_actions(None)}"
            "</div>"
        )

    series = data.active
    countdown = _countdown(series, today)
    rate = format_rate_range(series.rate) or "–"
    ehm = format_percent(series.ehm) or "–"
    tenor = (
        series.tenor.replace("Y", " év").replace("M", " hónap")
        if series.tenor
        else "5 év"
    )
    metrics = "".join(
        [
            _metric("Kamat", rate),
            _metric("EHM", ehm),
            _metric("Futamidő", tenor),
            _metric("Lejárat", format_date_hu(series.maturity) if series.maturity else "–"),
            _metric("Értékesítés", _date_range(series)),
            _metric("ISIN", series.isin or "–"),
            _metric("Vételár", "100% + felhalmozott kamat + díj"),
            _metric("Státusz", countdown or "Aktív"),
        ]
    )
    return (
        '<div class="card hero-card">'
        '<p class="eyebrow">Jelenleg kapható</p>'
        f"<h1>{_e(series.name)}</h1>"
        '<p class="lead">5 éves futamidő, fix sávos kamatozás, 1 Ft-os alapcímlet.</p>'
        f'<div class="metrics">{metrics}</div>'
        f'<p class="note">{_e(PURCHASE_PRICE_NOTE)}.</p>'
        f"{_series_actions(series)}"
        "</div>"
    )


def _sidebar(data: DashboardData, today: date) -> str:
    upcoming_html = []
    for series in data.upcoming[:2]:
        rate = format_rate_range(series.rate) or "–"
        ehm = format_percent(series.ehm) or "–"
        countdown = _countdown(series, today) or ""
        upcoming_html.append(
            '<div class="upcoming-item">'
            f'<div class="kicker">Hamarosan indul</div>'
            f'<h2>{_e(series.name)}</h2>'
            f'<div class="row"><span>Kezdés</span><strong>{_e(format_date_hu(series.start))}</strong></div>'
            f'<div class="row"><span>Kamat</span><strong>{_e(rate)}</strong></div>'
            f'<div class="row"><span>EHM</span><strong>{_e(ehm)}</strong></div>'
            f'<div class="row"><span>Státusz</span><strong>{_e(countdown)}</strong></div>'
            "</div>"
        )
    if not upcoming_html:
        upcoming_html.append(
            '<div class="upcoming-item">'
            '<div class="kicker">Hamarosan indul</div>'
            "<h2>Nincs kihirdetett sorozat</h2>"
            '<p class="note">A következő sorozat kihirdetésekor értesítést küldünk.</p>'
            "</div>"
        )

    return (
        '<aside class="sidebar">'
        f'<div class="card">{"".join(upcoming_html)}</div>'
        '<div class="card">'
        '<div class="kicker">Állapot</div>'
        f'<div class="row"><span>Utolsó frissítés</span><strong>{_e(format_datetime_hu(data.generated_at))}</strong></div>'
        '<div class="row"><span>Adatforrás</span><strong>ÁKK</strong></div>'
        '<div class="row"><span>Frissítés</span><strong>igény szerint</strong></div>'
        '<div class="row"><span>Automatizálás</span><strong>GitHub Actions</strong></div>'
        f'<p class="note"><a href="{_e(GITHUB_URL)}" target="_blank" rel="noopener">GitHub repó</a></p>'
        "</div>"
        "</aside>"
    )


def _chart_svg(history: list[RetailSeries]) -> str:
    points: list[tuple[date, float, str]] = []
    for row in sorted(history, key=lambda item: item.valid_from):
        value = to_float(row.ehm)
        if value is None and row.rate:
            value = to_float(row.rate.split("-")[0])
        if value is not None:
            points.append((row.valid_from, value, row.name))
    points = points[-12:]
    if not points:
        return '<p class="note">Nincs elegendő kamatadat a grafikonhoz.</p>'
    if len(points) == 1:
        return (
            '<p class="note">Jelenleg csak egy sorozathoz van kamatadat: '
            f"{_e(format_date_hu(points[0][0]))} – {_e(format_percent(points[0][1]))}.</p>"
        )

    width, height = 900, 270
    left, right, top, bottom = 58, 22, 20, 38
    plot_w = width - left - right
    plot_h = height - top - bottom
    values = [item[1] for item in points]
    min_v = min(values) - 0.35
    max_v = max(values) + 0.35
    if max_v - min_v < 0.5:
        min_v -= 0.25
        max_v += 0.25

    def x_pos(index: int) -> float:
        return left + (plot_w * index / (len(points) - 1))

    def y_pos(value: float) -> float:
        return top + (max_v - value) / (max_v - min_v) * plot_h

    grid_parts: list[str] = []
    for step in range(5):
        value = min_v + (max_v - min_v) * step / 4
        y = y_pos(value)
        grid_parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" '
            'stroke="#3f4147" stroke-width="1" />'
        )
        grid_parts.append(
            f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'fill="#949ba4" font-size="11">{_e(format_percent(value))}</text>'
        )

    coords = [(x_pos(index), y_pos(value)) for index, (_, value, _) in enumerate(points)]
    line_path = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    base_y = top + plot_h
    area_path = (
        f"M {coords[0][0]:.1f},{base_y:.1f} L "
        + " L ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
        + f" L {coords[-1][0]:.1f},{base_y:.1f} Z"
    )
    circles = []
    for index, (point_date, value, name) in enumerate(points):
        x, y = coords[index]
        circles.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#2ecc71">'
            f"<title>{_e(name)} – {_e(format_date_hu(point_date))}: {_e(format_percent(value))}</title>"
            "</circle>"
        )
    labels = []
    if len(points) >= 2:
        indexes = sorted({0, len(points) // 2, len(points) - 1})
        for index in indexes:
            point_date = points[index][0]
            x = x_pos(index)
            labels.append(
                f'<text x="{x:.1f}" y="{height - 12}" text-anchor="middle" '
                f'fill="#949ba4" font-size="11">{point_date.year}. {point_date.month:02d}.</text>'
            )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        'aria-label="A MÁP+ sorozatok induláskori EHM-jének alakulása">'
        "<defs><linearGradient id=\"areaGradient\" x1=\"0\" y1=\"0\" x2=\"0\" y2=\"1\">"
        '<stop offset="0%" stop-color="#2ecc71" stop-opacity="0.28" />'
        '<stop offset="100%" stop-color="#2ecc71" stop-opacity="0.02" />'
        "</linearGradient></defs>"
        + "".join(grid_parts)
        + f'<path d="{area_path}" fill="url(#areaGradient)" />'
        + f'<path d="{line_path}" fill="none" stroke="#2ecc71" stroke-width="2.5" '
        'stroke-linejoin="round" stroke-linecap="round" />'
        + "".join(circles)
        + "".join(labels)
        + "</svg>"
    )


def _history_table(data: DashboardData) -> str:
    if not data.history:
        return '<p class="note">Nincs korábbi MÁP+ sorozat az adatok között.</p>'
    rows = []
    for row in data.history:
        pdf_url = data.pdf_by_name.get(row.name) or data.pdf_by_name.get(
            series_name_key(row.name)
        )
        pdf = (
            f'<a href="{_e(pdf_url)}" target="_blank" rel="noopener">PDF</a>'
            if pdf_url
            else "–"
        )
        ehm = format_percent(row.ehm) or "–"
        rows.append(
            "<tr>"
            f"<td><strong>{_e(row.name)}</strong></td>"
            f"<td>{_e(format_date_hu(row.valid_from))} – "
            f"{_e(format_date_hu(row.valid_to)) if row.valid_to else 'visszavonásig'}</td>"
            f"<td>{_e(format_rate_range(row.rate) or '–')}</td>"
            f"<td>{_e(ehm)}</td>"
            f"<td>{_e(format_date_hu(row.maturity)) if row.maturity else '–'}</td>"
            f"<td>{pdf}</td>"
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table>'
        "<thead><tr><th>Sorozat</th><th>Értékesítés</th><th>Kamat</th><th>EHM</th><th>Lejárat</th><th>PDF</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def _comparison_table(data: DashboardData) -> str:
    if not data.products:
        return '<p class="note">Nincs összehasonlítható adat.</p>'
    rows = []
    for row in data.products:
        label = _product_label(row.row_type)
        css = ' class="map"' if label == "MÁP+" else ""
        ehm = format_percent(row.ehm) or "–"
        rows.append(
            f"<tr{css}>"
            f"<td><span class=\"badge\">{_e(label)}</span></td>"
            f"<td>{_e(row.name)}</td>"
            f"<td>{_e(format_rate_range(row.rate) or '–')}</td>"
            f"<td>{_e(ehm)}</td>"
            f"<td>{_e(format_date_hu(row.maturity)) if row.maturity else '–'}</td>"
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table>'
        "<thead><tr><th>Típus</th><th>Sorozat</th><th>Kamat</th><th>EHM</th><th>Lejárat</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def _default_rate(data: DashboardData) -> float:
    if data.active and data.active.rate:
        value = to_float(data.active.rate.split("-")[0].strip())
        if value is not None:
            return value
    return 5.0


def _calculator(data: DashboardData) -> str:
    rate = _default_rate(data)
    return f"""
    <div class="calc">
      <label>Befektetett összeg (Ft)
        <input id="calc-amount" type="number" min="0" step="10000" value="1000000" inputmode="numeric">
      </label>
      <label>Éves kamat (%)
        <input id="calc-rate" type="number" min="0" step="0.01" value="{rate:.2f}" inputmode="decimal">
      </label>
      <label>Évek
        <input id="calc-years" type="number" min="1" max="5" step="1" value="5" inputmode="numeric">
      </label>
    </div>
    <div class="calc-results">
      <div><span>Éves kamat</span><strong id="calc-yearly">–</strong></div>
      <div><span>Összes kamat</span><strong id="calc-total">–</strong></div>
      <div><span>Lejáratkor</span><strong id="calc-final">–</strong></div>
    </div>
    <p class="note">Az első évi kamattal számol. A MÁP+ sávos kamatozású, ezért a későbbi évek kamata a hivatalos nyilvános ajánlattételben szerepel.</p>
    """


def render_html(
    data: DashboardData,
    config: Config,
    show_calculator: bool = True,
) -> str:
    today = data.generated_at.date()
    calculator = _calculator(data)
    calculator_nav = (
        '<a href="#kalkulator">Kalkulátor</a>' if show_calculator else ""
    )
    calculator_section = (
        '<section id="kalkulator" class="section card">'
        '<div class="section-title"><h2>Hozamkalkulátor</h2>'
        "<span>Becslés az első évi kamattal</span></div>"
        f"{calculator}</section>"
        if show_calculator
        else ""
    )
    warning = ""
    if data.source_errors:
        warning = (
            '<div class="warning">Részleges adatlekérési hiba: '
            + _e("; ".join(data.source_errors))
            + "</div>"
        )
    return f"""<!doctype html>
<html lang="hu">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MÁP+ Watcher – aktuális sorozat</title>
<meta name="description" content="MÁP+ állampapír sorozatok, kamatok, előzmények és hozamkalkulátor.">
<style>{CSS}</style>
</head>
<body>
<div class="container">
  <header class="topbar">
    <div class="brand"><span class="brand-mark">MÁP+</span><span>MÁP+ Watcher</span></div>
    <nav class="topnav">
      <a href="#attekintes">Áttekintés</a>
      <a href="#arak">Kamatok</a>
      <a href="#elozmenyek">Előzmények</a>
      <a href="#osszehasonlitas">Összehasonlítás</a>
      {calculator_nav}
      <a href="{_e(GITHUB_URL)}" target="_blank" rel="noopener">GitHub</a>
    </nav>
  </header>
  <main>
    {warning}
    <section id="attekintes" class="hero">
      {_hero(data, today)}
      {_sidebar(data, today)}
    </section>
    <section id="arak" class="section card">
      <div class="section-title"><h2>EHM alakulása</h2><span>A sorozatok induláskori EHM-je</span></div>
      <div class="chart">{_chart_svg(data.history)}</div>
    </section>
    <section id="elozmenyek" class="section card">
      <div class="section-title"><h2>Korábbi sorozatok</h2><span>Utolsó 12 sorozat</span></div>
      {_history_table(data)}
    </section>
    <section id="osszehasonlitas" class="section card">
      <div class="section-title"><h2>MÁP+ és más állampapírok</h2><span>Jelenlegi lakossági kamatok</span></div>
      {_comparison_table(data)}
      <p class="note">A többi termék adatai tájékoztató jellegűek. A MÁP+ részleteit a hivatalos nyilvános ajánlattétel tartalmazza.</p>
    </section>
    {calculator_section}
  </main>
  <footer>
    <p>Az adatok tájékoztató jellegűek, nem befektetési tanács. Forrás: ÁKK nyilvános adatai. Vásárlás előtt ellenőrizd a hivatalos nyilvános ajánlattételt.</p>
    <p><a href="{_e(GITHUB_URL)}" target="_blank" rel="noopener">GitHub</a> · <a href="{_e(OFFERING_PAGE)}" target="_blank" rel="noopener">Nyilvános ajánlattételek</a> · <a href="{_e(WEBKINCSTAR_URL)}" target="_blank" rel="noopener">WebKincstár</a></p>
  </footer>
</div>
<script>{CALCULATOR_JS}</script>
</body>
</html>
"""


def write_dashboard(
    data: DashboardData,
    config: Config,
    output_dir: Path,
    show_calculator: bool = True,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / "index.html"
    index_path.write_text(
        render_html(data, config, show_calculator=show_calculator),
        encoding="utf-8",
    )

    ics_series = ([data.active] if data.active else []) + data.upcoming
    ics = build_ics(
        ics_series,
        generated_at=data.generated_at,
        page_url=config.app.public_url,
    )
    ics_path = output_dir / "map-plusz.ics"
    with ics_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(ics)

    payload = {
        "generated_at": data.generated_at.isoformat(),
        "active": data.active.to_dict() if data.active else None,
        "upcoming": [item.to_dict() for item in data.upcoming],
        "history": [item.to_dict() for item in data.history],
        "products": [item.to_dict() for item in data.products],
        "source_errors": data.source_errors,
    }
    (output_dir / "data.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return index_path


CSS = """
:root {
  --bg: #17181b;
  --panel: #202226;
  --panel-2: #2b2d31;
  --text: #dbdee1;
  --strong: #f2f3f5;
  --muted: #949ba4;
  --green: #2ecc71;
  --blue: #00a8fc;
  --border: #3f4147;
  --button: #4e5058;
  --danger: #e74c3c;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: radial-gradient(1100px 700px at 15% -10%, #26282d 0%, var(--bg) 55%);
  color: var(--text);
  font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--blue); text-decoration: none; }
a:hover { text-decoration: underline; }
.container { max-width: 1180px; margin: 0 auto; padding: 22px 24px 0; }
.topbar { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 6px 0 24px; }
.brand { display: flex; align-items: center; gap: 11px; color: var(--strong); font-weight: 700; font-size: 16px; }
.brand-mark {
  width: 38px; height: 38px; border-radius: 50%;
  background: linear-gradient(145deg, #2ecc71 0%, #1f8f4d 55%, #153f2a 100%);
  display: inline-flex; align-items: center; justify-content: center;
  color: #fff; font-size: 10px; font-weight: 800; letter-spacing: -.03em;
}
.topnav { display: flex; gap: 18px; font-size: 13px; }
.topnav a { color: var(--muted); }
.topnav a:hover { color: var(--strong); text-decoration: none; }
.hero { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(290px, .85fr); gap: 18px; }
.card {
  background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
  padding: 22px;
}
.hero-card { border-left: 4px solid var(--green); }
.eyebrow { margin: 0 0 8px; color: var(--green); font-size: 11px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
h1 { margin: 0 0 4px; font-size: 42px; letter-spacing: -.03em; }
h2 { margin: 0; font-size: 22px; }
.lead { margin: 0 0 18px; color: var(--muted); }
.metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.metric { background: var(--panel-2); border: 1px solid var(--border); border-radius: 7px; padding: 10px 12px; min-width: 0; }
.metric .label { color: var(--muted); font-size: 10px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; margin-bottom: 4px; }
.metric .value { font-size: 14px; overflow-wrap: anywhere; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 18px; }
.btn {
  display: inline-block; padding: 9px 13px; border-radius: 5px;
  background: var(--button); color: #fff; font-size: 12.5px; font-weight: 600;
}
.btn:hover { text-decoration: none; filter: brightness(1.08); }
.btn.primary { background: var(--green); color: #07130c; }
.btn.blue { background: var(--blue); color: #04141c; }
.note { color: var(--muted); font-size: 12px; line-height: 1.55; }
.sidebar { display: flex; flex-direction: column; gap: 18px; }
.upcoming-item + .upcoming-item { border-top: 1px solid var(--border); margin-top: 14px; padding-top: 14px; }
.kicker { color: var(--muted); font-size: 10px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
.sidebar h2 { font-size: 24px; margin: 6px 0 10px; }
.row { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 13px; }
.row:last-child { border-bottom: 0; }
.row span { color: var(--muted); }
.row strong { text-align: right; font-weight: 600; }
.section { margin-top: 18px; }
.section-title { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.section-title span { color: var(--muted); font-size: 12px; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; color: var(--muted); font-size: 10px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; padding: 8px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; }
td { padding: 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
tr:last-child td { border-bottom: 0; }
tr.map td { background: rgba(46, 204, 113, .06); }
.badge { display: inline-block; border: 1px solid var(--border); border-radius: 999px; padding: 2px 8px; font-size: 11px; color: var(--muted); white-space: nowrap; }
.chart svg { width: 100%; height: auto; display: block; }
.calc { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.calc label { display: flex; flex-direction: column; gap: 6px; color: var(--muted); font-size: 12px; }
.calc input { width: 100%; background: var(--panel-2); border: 1px solid var(--border); border-radius: 5px; color: var(--text); padding: 10px; font-size: 15px; }
.calc input:focus { outline: 1px solid var(--green); border-color: var(--green); }
.calc-results { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-top: 18px; }
.calc-results div { background: var(--panel-2); border: 1px solid var(--border); border-radius: 7px; padding: 12px; }
.calc-results span { display: block; color: var(--muted); font-size: 11px; margin-bottom: 4px; }
.calc-results strong { font-size: 20px; }
.warning { border-left: 3px solid var(--danger); background: rgba(231, 76, 60, .08); padding: 10px 14px; border-radius: 4px; margin-bottom: 18px; font-size: 13px; }
footer { color: var(--muted); font-size: 12px; line-height: 1.7; padding: 34px 0 26px; }
footer p { margin: 0 0 6px; }
@media (max-width: 900px) {
  .hero { grid-template-columns: 1fr; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .calc, .calc-results { grid-template-columns: 1fr; }
  h1 { font-size: 34px; }
  .topnav { display: none; }
}
@media (max-width: 560px) {
  .container { padding: 16px 14px 0; }
  .card { padding: 16px; }
  .metrics { grid-template-columns: 1fr; }
  h1 { font-size: 30px; }
  .section-title { display: block; }
  .section-title span { display: block; margin-top: 4px; }
}
"""

CALCULATOR_JS = """
(function () {
  const amount = document.getElementById('calc-amount');
  const rate = document.getElementById('calc-rate');
  const years = document.getElementById('calc-years');
  const yearly = document.getElementById('calc-yearly');
  const total = document.getElementById('calc-total');
  const final = document.getElementById('calc-final');
  if (!amount || !rate || !years) return;

  function numberValue(input) {
    const value = Number(String(input.value).replace(',', '.'));
    return Number.isFinite(value) ? value : 0;
  }
  function formatFt(value) {
    return new Intl.NumberFormat('hu-HU', {
      style: 'currency',
      currency: 'HUF',
      maximumFractionDigits: 0
    }).format(value);
  }
  function update() {
    const a = numberValue(amount);
    const r = numberValue(rate) / 100;
    const y = Math.max(1, Math.min(5, numberValue(years)));
    if (a < 0 || r < 0) {
      yearly.textContent = '–';
      total.textContent = '–';
      final.textContent = '–';
      return;
    }
    const oneYear = a * r;
    const all = oneYear * y;
    yearly.textContent = formatFt(oneYear);
    total.textContent = formatFt(all);
    final.textContent = formatFt(a + all);
  }
  [amount, rate, years].forEach(function (input) {
    input.addEventListener('input', update);
  });
  update();
})();
"""
