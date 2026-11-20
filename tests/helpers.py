from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from allampapir_ertesito.config import (
    AppSettings,
    Config,
    ConsoleSettings,
    DiscordSettings,
    EmailSettings,
    NtfySettings,
    ReminderSettings,
    TelegramSettings,
    WebhookSettings,
    WindowsSettings,
)
from allampapir_ertesito.models import Message, Offering, RetailSeries
from allampapir_ertesito.notifiers.base import Notifier


class FakeClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def now(self) -> datetime:
        return self.current


class FakeNotifier(Notifier):
    name = "fake"

    def __init__(self) -> None:
        self.messages: list[Message] = []

    def send(self, message: Message) -> None:
        self.messages.append(message)


class FailingNotifier(Notifier):
    name = "failing"

    def send(self, message: Message) -> None:
        raise RuntimeError("szándékos hiba")


class FakeClient:
    def __init__(
        self,
        offerings: list[Offering] | None = None,
        retail: list[RetailSeries] | None = None,
        offerings_error: Exception | None = None,
        retail_error: Exception | None = None,
    ) -> None:
        self.offerings = offerings or []
        self.retail = retail or []
        self.offerings_error = offerings_error
        self.retail_error = retail_error

    def fetch_offerings(self, today: date, lookback_days: int = 730, horizon_days: int = 120):
        if self.offerings_error is not None:
            raise self.offerings_error
        return list(self.offerings)

    def fetch_retail(self, today: date, lookback_days: int = 730):
        if self.retail_error is not None:
            raise self.retail_error
        return list(self.retail)


def make_config(tmp_path: Path, **overrides) -> Config:
    app = AppSettings(
        first_run_notify=True,
        announce_new_offerings=True,
        notify_on_start=True,
        ending_soon_days=14,
        notify_on_error=False,
        state_file=tmp_path / "state.json",
        log_file=None,
        timezone="UTC",
        lookback_days=730,
        announce_horizon_days=120,
        http_timeout_seconds=30,
        public_url="",
    )
    reminder = ReminderSettings(enabled=False, delay_hours=24, text="Fizesd be a vételárat.")
    config = Config(
        path=tmp_path / "config.toml",
        app=app,
        console=ConsoleSettings(enabled=False),
        ntfy=NtfySettings(enabled=False),
        email=EmailSettings(enabled=False),
        telegram=TelegramSettings(enabled=False),
        discord=DiscordSettings(enabled=False),
        windows=WindowsSettings(enabled=False),
        webhook=WebhookSettings(enabled=False),
        reminder=reminder,
    )
    for key, value in overrides.items():
        setattr(config, key, value)
        if key == "app":
            config.app = value
        if key == "reminder":
            config.reminder = value
    return config


def make_offering(
    name: str,
    start: date,
    end: date | None,
    published: datetime | None = None,
    rate: str = "5.00 - 6.00",
    coupon: float | None = 5.0,
    isin: str | None = "HU0000000001",
) -> Offering:
    if published is None:
        published = datetime.combine(start - timedelta(days=5), time(13, 30))
    maturity = date(start.year + 5, start.month, min(start.day, 27))
    return Offering(
        name=name,
        start_period=start,
        end_period=end,
        published=published,
        maturity=maturity,
        coupon=coupon,
        rate_text=rate,
        isin=isin,
        pdf_path=f"public_offerings/{name.replace('/', '-')}.pdf",
        label="MÁPP_T",
        archive=False,
    )


def make_retail(
    name: str,
    valid_from: date,
    valid_to: date | None,
    rate: str = "5.00 - 6.00",
    ehm: str = "5.47",
) -> RetailSeries:
    maturity = date(valid_from.year + 5, valid_from.month, min(valid_from.day, 27))
    return RetailSeries(
        name=name,
        valid_from=valid_from,
        valid_to=valid_to,
        rate=rate,
        ehm=ehm,
        maturity=maturity,
        tenor="5Y",
        row_type="MÁP Plusz",
    )


def utc(year: int, month: int, day: int, hour: int = 10, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
