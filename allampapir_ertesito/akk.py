"""Az ÁKK nyilvános adatforrásainak klienssel és feldolgozóival.

Két végpontot használunk:

* ``getPublicOfferings`` – a MÁP+ sorozatok nyilvános ajánlattételei.
  Itt jelenik meg először egy új sorozat, jellemzően néhány nappal a
  vásárlási időszak kezdete előtt.
* ``getRetailInterestExt`` – a jelenleg értékesítés alatt álló lakossági
  állampapírok kamatai. Innen jön a pontossabb kamat/EHM adat, és ez a
  tartalék forrás, ha az ajánlattételi lista késik.

Az ÁKK nem hivatalos, dokumentált API-ját használjuk. Ha a végpont vagy a
válasz szerkezete megváltozik, a program hibát jelez a naplóban.
"""

from __future__ import annotations

import gzip
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from .models import Offering, RetailSeries
from .util import is_map_plusz_type, parse_date, parse_datetime, to_float

logger = logging.getLogger("allampapir.akk")

API_URL = "https://www.akk.hu/api/data/xpose3-dwh/data"
DEFAULT_USER_AGENT = "AllampapirErtesito/1.0 (personal monitoring)"
MAPP_LABEL = "MAPP_T"


class AkkError(RuntimeError):
    """Az ÁKK adatlekérése vagy feldolgozása sikertelen."""


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "igen", "yes"}
    return bool(value)


def parse_offerings(rows: Iterable[dict[str, Any]]) -> list[Offering]:
    """A getPublicOfferings válasz sorainak feldolgozása és deduplikálása."""
    parsed: list[Offering] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = _clean(row.get("name")) or _clean(row.get("offeringName"))
        start = parse_date(row.get("startPeriod"))
        if not name or start is None:
            continue
        parsed.append(
            Offering(
                name=name,
                start_period=start,
                end_period=parse_date(row.get("endPeriod")),
                published=parse_datetime(row.get("published")),
                maturity=parse_date(row.get("maturity")),
                coupon=to_float(row.get("coupon")),
                rate_text=_clean(row.get("ehmString")),
                ehm=to_float(row.get("ehm")),
                isin=_clean(row.get("isin")),
                pdf_path=_clean(row.get("path")),
                label=_clean(row.get("label")),
                archive=_as_bool(row.get("archive")),
                modified_on=parse_datetime(row.get("modifiedOn")),
            )
        )
    return dedupe_offerings(parsed)


def dedupe_offerings(offerings: Iterable[Offering]) -> list[Offering]:
    """Egy sorozatból a legfrissebb közzétételt tartja meg.

    Az ÁKK ugyanarra a sorozatra több ajánlattételt is közzétehet
    (módosítás, hosszabbítás). A (név, kezdőnap) páros azonosítja a sorozatot;
    a legkésőbb publikált változat a mérvadó.
    """
    best: dict[tuple[str, date], Offering] = {}
    for offering in offerings:
        key = (offering.name, offering.start_period)
        current = best.get(key)
        if current is None or _offering_version(offering) >= _offering_version(current):
            best[key] = offering
    return sorted(best.values(), key=lambda item: (item.start_period, item.name))


def _offering_version(offering: Offering) -> tuple[datetime, datetime]:
    return (
        offering.published or datetime.min,
        offering.modified_on or datetime.min,
    )


def parse_retail(rows: Iterable[dict[str, Any]]) -> list[RetailSeries]:
    """A getRetailInterestExt válasz sorainak feldolgozása."""
    parsed: list[RetailSeries] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = _clean(row.get("name"))
        valid_from = parse_date(row.get("validFrom"))
        if not name or valid_from is None:
            continue
        parsed.append(
            RetailSeries(
                name=name,
                valid_from=valid_from,
                valid_to=parse_date(row.get("validTo")),
                rate=_clean(row.get("rate")),
                ehm=_clean(row.get("ehm")),
                maturity=parse_date(row.get("maturity")),
                tenor=_clean(row.get("tenor")),
                row_type=_clean(row.get("type")),
            )
        )
    # Azonos (név, kezdőnap) esetén az utolsó sor a friss.
    deduped: dict[tuple[str, date], RetailSeries] = {}
    for series in parsed:
        deduped[(series.name, series.valid_from)] = series
    return sorted(deduped.values(), key=lambda item: (item.valid_from, item.name))


class AkkClient:
    """Az ÁKK adatlekérések kis, újrapróbálkozó kliense."""

    def __init__(
        self,
        timeout: int = 30,
        retries: int = 2,
        user_agent: str = DEFAULT_USER_AGENT,
        base_url: str = API_URL,
    ) -> None:
        self.timeout = timeout
        self.retries = max(0, retries)
        self.user_agent = user_agent
        self.base_url = base_url

    def fetch_offerings(
        self,
        today: date,
        lookback_days: int = 730,
        horizon_days: int = 120,
    ) -> list[Offering]:
        """A közelmúltban kihirdetett és a közeljövőben induló MÁP+ ajánlattételek."""
        params = {
            "query": "getPublicOfferings",
            "label": MAPP_LABEL,
            "ptsStart": (today - timedelta(days=lookback_days)).isoformat(),
            "ptsEnd": (today + timedelta(days=horizon_days)).isoformat(),
        }
        payload = self._get_json(params)
        rows = self._data_rows(payload, "getPublicOfferings")
        return parse_offerings(rows)

    def fetch_retail(
        self,
        today: date,
        lookback_days: int = 730,
    ) -> list[RetailSeries]:
        """A MÁP+ sorozatok aktuális és közelmúltbeli kamatadatai."""
        params = {
            "query": "getRetailInterestExt",
            "type": "MÁP Plusz",
            "validFrom": (today - timedelta(days=lookback_days)).isoformat(),
        }
        payload = self._get_json(params)
        rows = self._data_rows(payload, "getRetailInterestExt")
        series = parse_retail(rows)

        if not series:
            # Ha az ÁKK megváltoztatja a típus nevét, próbáljunk szűrés nélkül.
            fallback_params = {
                "query": "getRetailInterestExt",
                "validFrom": (today - timedelta(days=lookback_days)).isoformat(),
            }
            payload = self._get_json(fallback_params)
            rows = self._data_rows(payload, "getRetailInterestExt")
            series = [
                item for item in parse_retail(rows) if is_map_plusz_type(item.row_type)
            ]
            if series:
                logger.warning(
                    "A MÁP+ típusra szűrt lekérés üres volt; szűrés nélkül "
                    "találtam %d sort. Az ÁKK megváltoztathatta a típus nevét.",
                    len(series),
                )
        return series

    def _get_json(self, params: dict[str, Any]) -> dict[str, Any]:
        query = urllib.parse.urlencode(params, doseq=True)
        url = f"{self.base_url}?{query}"
        last_error: str = "ismeretlen hiba"

        for attempt in range(self.retries + 1):
            try:
                request = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": self.user_agent,
                        "Accept": "application/json, text/plain, */*",
                        "Accept-Encoding": "gzip, deflate, identity",
                    },
                )
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
                    raw = self._decompress(raw, response.headers.get("Content-Encoding"))
                    text = raw.decode("utf-8-sig")
                    try:
                        payload = json.loads(text)
                    except json.JSONDecodeError as exc:
                        preview = text[:200].replace("\n", " ")
                        raise AkkError(
                            "Az ÁKK API nem JSON választ adott. "
                            f"HTTP {getattr(response, 'status', '?')}, "
                            f"előnézet: {preview!r}"
                        ) from exc
                if not isinstance(payload, dict):
                    raise AkkError("Az ÁKK API válasza nem JSON objektum.")
                meta = payload.get("meta") or {}
                status = meta.get("status")
                if status not in (None, "OK"):
                    raise AkkError(
                        f"Az ÁKK API hibát jelzett: {status} – {meta.get('message')}"
                    )
                return payload
            except urllib.error.HTTPError as exc:
                last_error = f"HTTP {exc.code} {exc.reason}"
                body = ""
                try:
                    body = exc.read(500).decode("utf-8", "replace").strip()
                except OSError:
                    pass
                if body:
                    last_error += f" – {body[:300]}"
                # 4xx (kivéve 429) esetén nincs értelme ismételni.
                if 400 <= exc.code < 500 and exc.code != 429:
                    break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                reason = getattr(exc, "reason", exc)
                last_error = f"hálózati hiba: {reason}"
            except AkkError:
                raise
            except Exception as exc:  # védelem a nem várt klienshibák ellen
                last_error = f"{type(exc).__name__}: {exc}"

            if attempt < self.retries:
                delay = 2 ** attempt
                logger.warning(
                    "ÁKK lekérés sikertelen (%s), újrapróbálás %d mp múlva.",
                    last_error,
                    delay,
                )
                time.sleep(delay)

        raise AkkError(f"Nem sikerült elérni az ÁKK adatforrást: {last_error}")

    @staticmethod
    def _decompress(raw: bytes, content_encoding: str | None) -> bytes:
        encoding = (content_encoding or "").lower().strip()
        if encoding == "gzip":
            return gzip.decompress(raw)
        if encoding == "deflate":
            try:
                return zlib.decompress(raw)
            except zlib.error:
                return zlib.decompress(raw, -zlib.MAX_WBITS)
        if encoding in {"br", "zstd"}:
            raise AkkError(
                f"A szerver nem támogatott tömörítést használt ({encoding})."
            )
        return raw

    @staticmethod
    def _data_rows(payload: dict[str, Any], function_name: str) -> list[dict[str, Any]]:
        data = payload.get("data")
        if data is None:
            raise AkkError(
                f"A(z) {function_name} válaszban nincs 'data' mező. "
                "Az ÁKK megváltoztathatta az API-t."
            )
        if not isinstance(data, list):
            raise AkkError(
                f"A(z) {function_name} válasz 'data' mezője nem lista: {type(data).__name__}."
            )
        return [row for row in data if isinstance(row, dict)]
