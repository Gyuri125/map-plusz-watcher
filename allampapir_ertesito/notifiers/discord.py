"""Discord webhook értesítés."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from ..calendar import PUBLIC_URL
from ..config import DiscordSettings
from ..messages import (
    PAYMENT_NOTE,
    PRODUCT_FEATURES,
    PRODUCT_PAGE,
    PURCHASE_PRICE_NOTE,
    WEBKINCSTAR_URL,
)
from ..models import Message, SeriesInfo
from ..util import format_date_hu, format_datetime_hu, format_percent, format_rate_range
from .base import Notifier, NotifierError

_COLORS = {
    "announcement": 0x3498DB,
    "start": 0x2ECC71,
    "reminder": 0xE67E22,
    "error": 0xE74C3C,
    "first_run": 0x9B59B6,
    "test": 0x95A5A6,
}


class DiscordNotifier(Notifier):
    name = "discord"

    def __init__(self, settings: DiscordSettings, timeout: int = 30) -> None:
        self.settings = settings
        self.timeout = timeout

    def send(self, message: Message) -> None:
        if not self.settings.webhook_url:
            raise NotifierError("Nincs beállítva Discord webhook URL.")

        embed = self._build_embed(message)
        payload: dict[str, object] = {
            "username": self.settings.username or "MÁP+ értesítő",
            "embeds": [embed],
            "allowed_mentions": {"parse": []},
        }
        if self.settings.avatar_url:
            payload["avatar_url"] = self.settings.avatar_url

        components = self._build_buttons(message)
        if components:
            payload["components"] = [{"type": 1, "components": components}]

        self._execute(payload, use_components=bool(components))

    def _execute(self, payload: dict[str, object], use_components: bool) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self._webhook_url_with_components() if use_components else self.settings.webhook_url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response.read(200)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(500).decode("utf-8", "replace").strip()
            except OSError:
                pass
            if use_components and exc.code == 400 and "component" in detail.lower():
                # Ha a Discord mégis elutasítja a gombokat, essünk vissza
                # gombok nélküli kártyára, hogy az értesítés ne vesszen el.
                fallback = dict(payload)
                fallback.pop("components", None)
                self._execute(fallback, use_components=False)
                return
            raise NotifierError(
                f"Discord HTTP {exc.code}: {self._redact(detail or str(exc.reason))}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise NotifierError(
                f"Discord hálózati hiba: {self._redact(str(exc))}"
            ) from exc

    def _build_embed(self, message: Message) -> dict[str, object]:
        series = message.series
        embed: dict[str, object] = {
            "title": self._truncate(message.title, 256),
            "color": _COLORS.get(message.event, 0x3498DB),
            "footer": {"text": "MÁP+ Watcher | nem befektetési tanács"},
            "timestamp": message.created_at.isoformat(),
        }

        if series is None:
            embed["description"] = self._truncate(message.body, 4096)
            return embed

        if message.event == "first_run":
            # Az első összefoglaló egyszerre mutatja az aktív és a következő
            # sorozatot, ezért itt a teljes szöveg a legjobb.
            embed["description"] = self._truncate(message.body, 4096)
            embed["url"] = series.pdf_url or PRODUCT_PAGE
            return embed

        intro = message.body.split("\n\n", 1)[0].strip()
        countdown = self._find_countdown(message.body)
        description = intro
        if countdown:
            description = f"{description}\n\n**{countdown}**"
        embed["description"] = self._truncate(description, 4096)
        embed["url"] = series.pdf_url or PRODUCT_PAGE
        embed["fields"] = self._series_fields(series, message)
        return embed

    def _series_fields(
        self,
        series: SeriesInfo,
        message: Message,
    ) -> list[dict[str, object]]:
        rate = format_rate_range(series.rate) or "–"
        ehm = format_percent(series.ehm) or "–"
        end = format_date_hu(series.end) if series.end else "visszavonásig"
        fields: list[dict[str, object]] = [
            {"name": "Sorozat", "value": series.name, "inline": True},
            {"name": "Kamat", "value": rate, "inline": True},
            {"name": "EHM", "value": ehm, "inline": True},
            {
                "name": "Értékesítés",
                "value": f"{format_date_hu(series.start)} – {end}",
                "inline": False,
            },
            {
                "name": "Lejárat",
                "value": format_date_hu(series.maturity) if series.maturity else "–",
                "inline": True,
            },
            {
                "name": "ISIN",
                "value": series.isin or "–",
                "inline": True,
            },
            {
                "name": "Futamidő",
                "value": (
                    series.tenor.replace("Y", " év").replace("M", " hónap")
                    if series.tenor
                    else "5 év"
                ),
                "inline": True,
            },
        ]
        if message.event == "announcement" and series.published:
            fields.append(
                {
                    "name": "Kihirdetve",
                    "value": format_datetime_hu(series.published),
                    "inline": False,
                }
            )
        links = [f"[WebKincstár]({WEBKINCSTAR_URL})"]
        if series.pdf_url:
            links.append(f"[Ajánlattétel]({series.pdf_url})")
        links.append(f"[Naptárba]({PUBLIC_URL}map-plusz.ics)")
        links.append(f"[AKK termékoldal]({PRODUCT_PAGE})")
        fields.extend(
            [
                {
                    "name": "Vételár",
                    "value": PURCHASE_PRICE_NOTE,
                    "inline": False,
                },
                {
                    "name": "Termék",
                    "value": PRODUCT_FEATURES,
                    "inline": False,
                },
                {
                    "name": "Linkek",
                    "value": " | ".join(links),
                    "inline": False,
                },
                {
                    "name": "Fizetés",
                    "value": PAYMENT_NOTE.removeprefix("Fizetés: "),
                    "inline": False,
                },
            ]
        )
        return fields

    @staticmethod
    def _find_countdown(body: str) -> str | None:
        for line in body.splitlines():
            text = line.strip()
            if text.startswith("Kezdésig:") or text.startswith("Hátralévő idő:"):
                return text
        return None

    @staticmethod
    def _build_buttons(message: Message) -> list[dict[str, object]]:
        series = message.series
        if series is None:
            return []
        buttons: list[dict[str, object]] = [
            {
                "type": 2,
                "style": 5,
                "label": "WebKincstár",
                "url": WEBKINCSTAR_URL,
            }
        ]
        if series.pdf_url:
            buttons.append(
                {
                    "type": 2,
                    "style": 5,
                    "label": "Ajánlattétel",
                    "url": series.pdf_url,
                }
            )
        buttons.append(
            {
                "type": 2,
                "style": 5,
                "label": "Naptárba",
                "url": f"{PUBLIC_URL}map-plusz.ics",
            }
        )
        buttons.append(
            {
                "type": 2,
                "style": 5,
                "label": "AKK termékoldal",
                "url": PRODUCT_PAGE,
            }
        )
        return buttons

    def _webhook_url_with_components(self) -> str:
        # A Discord webhookoknál a gombok csak ezzel a query paraméterrel
        # jelennek meg; enélkül a components mezőt csendben figyelmen kívül
        # hagyja a Discord.
        parts = urllib.parse.urlsplit(self.settings.webhook_url)
        query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
        query["with_components"] = "true"
        return urllib.parse.urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                urllib.parse.urlencode(query),
                parts.fragment,
            )
        )

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"

    def _redact(self, text: str) -> str:
        url = self.settings.webhook_url
        if url:
            return text.replace(url, "***")
        return text
