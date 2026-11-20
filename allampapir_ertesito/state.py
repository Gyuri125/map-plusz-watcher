"""Az értesítési állapot tartós tárolása.

Az állapotfájl akadályozza meg, hogy ugyanarról a sorozatról minden futáskor
újra értesítést küldjünk. Emellett itt tároljuk a vásárlási/fizetési
emlékeztetőket is.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import SeriesInfo
from .util import parse_date, parse_datetime

logger = logging.getLogger("allampapir.state")

STATE_VERSION = 1
MAX_HISTORY = 200


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _ensure_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@dataclass
class PendingReminder:
    series: SeriesInfo
    due_at: datetime
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "series": self.series.to_dict(),
            "due_at": self.due_at.isoformat(),
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PendingReminder | None":
        if not isinstance(data, dict):
            return None
        series_data = data.get("series")
        due_at = parse_datetime(data.get("due_at"))
        if not isinstance(series_data, dict) or due_at is None:
            return None
        name = str(series_data.get("name") or "").strip()
        start = parse_date(series_data.get("start"))
        if not name or start is None:
            return None
        text = str(data.get("text") or "").strip()
        if not text:
            return None
        series = SeriesInfo(
            name=name,
            start=start,
            end=parse_date(series_data.get("end")),
            published=parse_datetime(series_data.get("published")),
            maturity=parse_date(series_data.get("maturity")),
            rate=series_data.get("rate"),
            ehm=series_data.get("ehm"),
            isin=series_data.get("isin"),
            pdf_url=series_data.get("pdf_url"),
            source=str(series_data.get("source") or "offering"),
            tenor=series_data.get("tenor"),
        )
        return cls(
            series=series,
            due_at=_ensure_aware(due_at) or due_at,
            text=text,
        )


@dataclass
class State:
    version: int = STATE_VERSION
    last_check: datetime | None = None
    announced: list[str] = field(default_factory=list)
    started: list[str] = field(default_factory=list)
    # Sorozat neve -> az utolsó figyelmeztetésnél hátralévő napok száma.
    # Így a 14 napos figyelmeztetés után az utolsó napon még egyszer szólunk.
    ending_alerts: dict[str, int] = field(default_factory=dict)
    pending_reminders: list[PendingReminder] = field(default_factory=list)
    last_error_notified: datetime | None = None
    last_active: dict[str, Any] | None = None
    last_active_at: datetime | None = None

    @property
    def is_empty(self) -> bool:
        return (
            self.last_check is None
            and not self.announced
            and not self.started
            and not self.ending_alerts
            and not self.pending_reminders
        )

    def add_announced(self, name: str) -> None:
        self._add_unique(self.announced, name)

    def add_started(self, name: str) -> None:
        self._add_unique(self.started, name)

    def was_announced(self, name: str) -> bool:
        return name in self.announced

    def was_started(self, name: str) -> bool:
        return name in self.started

    def needs_ending_alert(self, name: str, days_left: int) -> bool:
        previous = self.ending_alerts.get(name)
        if previous is None:
            return True
        # A lejárat előtti figyelmeztetés után az utolsó napon is szólunk.
        return days_left == 0 and previous != 0

    def mark_ending_alert(self, name: str, days_left: int) -> None:
        self.ending_alerts[name] = days_left

    def add_reminder(self, reminder: PendingReminder) -> None:
        for existing in self.pending_reminders:
            if existing.series.name == reminder.series.name:
                return
        self.pending_reminders.append(reminder)

    def remove_reminder(self, reminder: PendingReminder) -> None:
        self.pending_reminders = [
            item for item in self.pending_reminders if item is not reminder
        ]

    @staticmethod
    def _add_unique(items: list[str], value: str) -> None:
        if not value or value in items:
            return
        items.append(value)
        if len(items) > MAX_HISTORY:
            del items[: len(items) - MAX_HISTORY]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": STATE_VERSION,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "announced": self.announced,
            "started": self.started,
            "ending_alerts": self.ending_alerts,
            "pending_reminders": [item.to_dict() for item in self.pending_reminders],
            "last_error_notified": (
                self.last_error_notified.isoformat() if self.last_error_notified else None
            ),
            "last_active": self.last_active,
            "last_active_at": (
                self.last_active_at.isoformat() if self.last_active_at else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "State":
        version = data.get("version")
        if version not in (None, STATE_VERSION):
            logger.warning(
                "Ismeretlen állapotfájl-verzió: %s (várt: %s). Megpróbálom betölteni.",
                version,
                STATE_VERSION,
            )
        reminders: list[PendingReminder] = []
        raw_reminders = data.get("pending_reminders")
        if isinstance(raw_reminders, list):
            for raw in raw_reminders:
                reminder = PendingReminder.from_dict(raw)
                if reminder is not None:
                    reminders.append(reminder)
        last_active = data.get("last_active")
        if not isinstance(last_active, dict):
            last_active = None
        ending_alerts: dict[str, int] = {}
        raw_ending = data.get("ending_alerts")
        if isinstance(raw_ending, dict):
            for name, value in raw_ending.items():
                try:
                    ending_alerts[str(name)] = int(value)
                except (TypeError, ValueError):
                    continue
        return cls(
            version=STATE_VERSION,
            last_check=_ensure_aware(parse_datetime(data.get("last_check"))),
            announced=_as_list(data.get("announced")),
            started=_as_list(data.get("started")),
            ending_alerts=ending_alerts,
            pending_reminders=reminders,
            last_error_notified=_ensure_aware(
                parse_datetime(data.get("last_error_notified"))
            ),
            last_active=last_active,
            last_active_at=_ensure_aware(parse_datetime(data.get("last_active_at"))),
        )


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> State:
        if not self.path.exists():
            return State()
        try:
            text = self.path.read_text(encoding="utf-8")
            data = json.loads(text)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Az állapotfájl nem olvasható (%s): %s", self.path, exc)
            self._backup_corrupt()
            return State()
        if not isinstance(data, dict):
            logger.error("Az állapotfájl tartalma nem JSON objektum: %s", self.path)
            self._backup_corrupt()
            return State()
        return State.from_dict(data)

    def save(self, state: State) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_name(self.path.name + ".tmp")
        payload = json.dumps(state.to_dict(), ensure_ascii=False, indent=2)
        try:
            temp_path.write_text(payload, encoding="utf-8")
            os.replace(temp_path, self.path)
        except OSError:
            logger.exception("Nem sikerült elmenteni az állapotfájlt: %s", self.path)
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass
            raise

    def _backup_corrupt(self) -> None:
        if not self.path.exists():
            return
        suffix = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = self.path.with_name(f"{self.path.name}.corrupt-{suffix}")
        try:
            os.replace(self.path, backup)
            logger.warning("A hibás állapotfájlt elmentettem ide: %s", backup)
        except OSError:
            logger.warning("A hibás állapotfájlt nem sikerült biztonságba helyezni.")
