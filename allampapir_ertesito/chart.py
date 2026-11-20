"""PNG grafikon az értesítésekhez: EHM-történet és termékösszehasonlítás."""

from __future__ import annotations

import os
from pathlib import Path

from .dashboard import DashboardData, _product_label
from .util import format_date_hu, format_percent, format_rate_range, to_float

_WIDTH = 1200
_HEIGHT = 920
_BG = "#0d1117"
_PANEL = "#161b22"
_TEXT = "#e6edf3"
_MUTED = "#8b949e"
_GRID = "#30363d"
_GREEN = "#3fb950"
_GREEN_DARK = "#12261a"
_ROW = "#1b222c"


class ChartError(RuntimeError):
    """A grafikon nem készíthető el."""


def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates = [
        windir / "Fonts" / ("segoeuib.ttf" if bold else "segoeui.ttf"),
        windir / "Fonts" / ("arialbd.ttf" if bold else "arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu")
        / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation")
        / ("LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _short_date(value) -> str:
    return f"{value.year}. {value.month:02d}."


def _history_points(data: DashboardData):
    rows = sorted(data.history, key=lambda item: item.valid_from)
    points = []
    for row in rows:
        value = to_float(row.ehm)
        if value is not None:
            points.append((row.valid_from, value, row.name))
    return points


def _draw_ehm_chart(draw, data: DashboardData, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    points = _history_points(data)
    if len(points) < 2:
        draw.text(
            ((x0 + x1) // 2, (y0 + y1) // 2),
            "Nincs elegendő EHM-adat a grafikonhoz.",
            font=_font(18),
            fill=_MUTED,
            anchor="mm",
        )
        return

    values = [value for _, value, _ in points]
    low = min(values)
    high = max(values)
    padding = max((high - low) * 0.18, 0.12)
    low -= padding
    high += padding

    def y_of(value: float) -> float:
        return y1 - (value - low) / (high - low) * (y1 - y0)

    def x_of(index: int) -> float:
        if len(points) == 1:
            return (x0 + x1) / 2
        return x0 + (x1 - x0) * index / (len(points) - 1)

    # Vízszintes segédvonalak és EHM-címkék.
    steps = 4
    for step in range(steps + 1):
        value = low + (high - low) * step / steps
        y = y_of(value)
        draw.line((x0, y, x1, y), fill=_GRID, width=1)
        label = format_percent(value) or ""
        draw.text((x0 - 12, y), label, font=_font(15), fill=_MUTED, anchor="rm")

    # Függőleges segédvonalak minden sorozat indulásánál.
    for index in range(len(points)):
        x = x_of(index)
        draw.line((x, y0, x, y1), fill="#21262d", width=1)

    # Terület és vonal.
    coords = [(x_of(i), y_of(value)) for i, (_, value, _) in enumerate(points)]
    area = coords + [(coords[-1][0], y1), (coords[0][0], y1)]
    draw.polygon(area, fill=_GREEN_DARK)
    draw.line(coords, fill=_GREEN, width=4, joint="curve")

    # Pontok, felettük a konkrét EHM-értékkel.
    for index, (_, value, _) in enumerate(points):
        x, y = coords[index]
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=_GREEN)
        label = format_percent(value) or ""
        label_y = y - 20
        if label_y < 118:
            label_y = y + 24
        draw.text(
            (x, label_y),
            label,
            font=_font(14, True),
            fill=_GREEN,
            anchor="mm",
        )

    # Dátum és sorozatnév minden pont alatt.
    for index, (day, _, name) in enumerate(points):
        x = x_of(index)
        draw.text(
            (x, y1 + 8),
            _short_date(day),
            font=_font(13),
            fill=_MUTED,
            anchor="ma",
        )
        draw.text(
            (x, y1 + 26),
            name,
            font=_font(12),
            fill=_TEXT,
            anchor="ma",
        )

    draw.line((x0, y1, x1, y1), fill=_GRID, width=1)
    draw.text(
        (x0, y0 - 45),
        "EHM az egyes sorozatok indulásakor",
        font=_font(16),
        fill=_MUTED,
    )


def _draw_products(draw, data: DashboardData, top: int) -> None:
    draw.text((64, top), "MÁP+ és más állampapírok", font=_font(24, True), fill=_TEXT)
    draw.text(
        (1136, top + 4),
        "Jelenlegi lakossági kamatok",
        font=_font(15),
        fill=_MUTED,
        anchor="ra",
    )

    header_y = top + 44
    columns = (
        (64, "Típus"),
        (250, "Sorozat"),
        (500, "Kamat"),
        (730, "EHM"),
        (850, "Lejárat"),
    )
    for x, label in columns:
        draw.text((x, header_y), label, font=_font(15, True), fill=_MUTED)
    draw.line((64, header_y + 24, 1136, header_y + 24), fill=_GRID, width=1)

    products = data.products[:6]
    if not products:
        draw.text(
            (64, header_y + 40),
            "Nincs összehasonlítható termékadat.",
            font=_font(17),
            fill=_MUTED,
        )
        return

    row_y = header_y + 34
    for index, product in enumerate(products):
        if index % 2 == 0:
            draw.rounded_rectangle(
                (56, row_y - 5, 1144, row_y + 29),
                radius=6,
                fill=_ROW,
            )
        label = _product_label(product.row_type)
        rate = format_rate_range(product.rate) or "–"
        ehm = format_percent(product.ehm) or "–"
        maturity = format_date_hu(product.maturity) if product.maturity else "–"
        color = _GREEN if label == "MÁP+" else _TEXT
        draw.text((64, row_y), label, font=_font(17, label == "MÁP+"), fill=color)
        draw.text((250, row_y), product.name, font=_font(17), fill=_TEXT)
        draw.text((500, row_y), rate, font=_font(17), fill=_TEXT)
        draw.text((730, row_y), ehm, font=_font(17), fill=_TEXT)
        draw.text((850, row_y), maturity, font=_font(17), fill=_TEXT)
        row_y += 34


def render_chart(data: DashboardData, path: Path) -> Path:
    """Elkészíti a PNG grafikont a megadott útvonalra."""
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:  # pragma: no cover - telepítésfüggő
        raise ChartError(
            "A grafikonhoz a Pillow csomag kell: pip install pillow"
        ) from exc

    image = Image.new("RGB", (_WIDTH, _HEIGHT), _BG)
    draw = ImageDraw.Draw(image)

    # Fejléc.
    draw.text((64, 38), "MÁP+ – EHM és összehasonlítás", font=_font(32, True), fill=_TEXT)
    generated = data.generated_at.strftime("%Y. %m. %d. %H:%M")
    draw.text(
        (1136, 48),
        f"Frissítve: {generated}",
        font=_font(15),
        fill=_MUTED,
        anchor="ra",
    )

    # Grafikonpanel.
    draw.rounded_rectangle((48, 100, 1152, 500), radius=14, fill=_PANEL)
    _draw_ehm_chart(draw, data, (100, 165, 1100, 395))

    # Összehasonlítás.
    _draw_products(draw, data, 550)

    # Lábléc.
    draw.line((64, 870, 1136, 870), fill=_GRID, width=1)
    draw.text(
        (64, 882),
        "Forrás: ÁKK nyilvános adatai. Nem befektetési tanács.",
        font=_font(14),
        fill=_MUTED,
    )
    draw.text(
        (1136, 882),
        "MÁP+ Watcher",
        font=_font(14, True),
        fill=_MUTED,
        anchor="ra",
    )

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG", optimize=True)
    return path
