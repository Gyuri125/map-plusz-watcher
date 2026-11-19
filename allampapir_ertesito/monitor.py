"""A figyelő logika: adatlekérés, döntés, értesítés, állapotkezelés."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .akk import AkkClient, AkkError
from .config import Config
from .messages import (
    build_announcement,
    build_error,
    build_first_run,
    build_reminder,
    build_start,
)
from .models import CheckOutcome, Message, Offering, RetailSeries, SeriesInfo
from .notifiers.base import NotifierManager
from .state import PendingReminder, State, StateStore
from .util import series_name_key

logger = logging.getLogger("allampapir.monitor")


class MonitorError(RuntimeError):
    """A figyelési ciklus nem tudta elvégezni a dolgát."""


class SystemClock:
    def __init__(self, timezone_name: str = "Europe/Budapest") -> None:
        self.timezone_name = timezone_name
        self.timezone = None
        if timezone_name:
            try:
                self.timezone = ZoneInfo(timezone_name)
            except Exception:
                logger.warning(
                    "A(z) %s időzóna nem érhető el; a helyi időt használom. "
                    "Windows alatt telepíthető a tzdata csomag.",
                    timezone_name,
                )

    def now(self) -> datetime:
        if self.timezone is not None:
            return datetime.now(self.timezone)
        return datetime.now().astimezone()


def select_active_offerings(
    offerings: list[Offering],
    today: date,
    now_naive: datetime | None = None,
) -> list[Offering]:
    active: list[Offering] = []
    for offering in offerings:
        if (
            now_naive is not None
            and offering.published is not None
            and offering.published > now_naive
        ):
            continue
        if offering.start_period <= today and (
            offering.end_period is None or offering.end_period >= today
        ):
            active.append(offering)
    return sorted(active, key=lambda item: (item.start_period, item.name))


def select_future_offerings(
    offerings: list[Offering],
    today: date,
    horizon_days: int,
    now_naive: datetime | None = None,
) -> list[Offering]:
    limit = today + timedelta(days=horizon_days)
    future: list[Offering] = []
    for offering in offerings:
        if (
            now_naive is not None
            and offering.published is not None
            and offering.published > now_naive
        ):
            continue
        if today < offering.start_period <= limit:
            future.append(offering)
    return sorted(future, key=lambda item: (item.start_period, item.name))


def match_retail(
    offering: Offering,
    retail: list[RetailSeries],
    today: date,
) -> RetailSeries | None:
    key = series_name_key(offering.name)
    candidates = [item for item in retail if series_name_key(item.name) == key]
    if not candidates:
        return None

    def score(item: RetailSeries) -> tuple[bool, bool, date]:
        covers_start = item.valid_from <= offering.start_period and (
            item.valid_to is None or item.valid_to >= offering.start_period
        )
        return (covers_start, item.is_active(today), item.valid_from)

    return max(candidates, key=score)


def merge_series(offering: Offering, retail: RetailSeries | None) -> SeriesInfo:
    return SeriesInfo.from_offering(offering, retail)


def latest_active_retail(retail: list[RetailSeries], today: date) -> RetailSeries | None:
    active = [item for item in retail if item.is_active(today)]
    if not active:
        return None
    return max(active, key=lambda item: (item.valid_from, item.name))


class Monitor:
    def __init__(
        self,
        config: Config,
        client: AkkClient,
        notifiers: NotifierManager,
        state_store: StateStore,
        clock: SystemClock | None = None,
    ) -> None:
        self.config = config
        self.client = client
        self.notifiers = notifiers
        self.state_store = state_store
        self.clock = clock or SystemClock(config.app.timezone)

    def check(self, dry_run: bool = False, force: bool = False) -> CheckOutcome:
        now = self.clock.now()
        today = now.date()
        now_naive = now.replace(tzinfo=None) if now.tzinfo else now
        state = self.state_store.load()
        first_run = state.is_empty
        outcome = CheckOutcome(dry_run=dry_run, first_run=first_run)

        logger.info("Ellenőrzés: %s", today.isoformat())

        # 1. Esedékes emlékeztetők kiküldése még az adatlekérés előtt.
        self._process_reminders(state, now, today, dry_run, outcome)

        # 2. Adatok lekérése. A két forrás egymástól függetlenül hibázhat.
        offerings: list[Offering] = []
        retail: list[RetailSeries] = []
        errors: list[str] = []

        try:
            offerings = self.client.fetch_offerings(
                today,
                lookback_days=self.config.app.lookback_days,
                horizon_days=self.config.app.announce_horizon_days,
            )
            logger.info("Ajánlattételek: %d sor", len(offerings))
        except AkkError as exc:
            errors.append(f"ajánlattételek: {exc}")
            logger.error("Ajánlattételi adatok lekérése sikertelen: %s", exc)

        try:
            retail = self.client.fetch_retail(
                today,
                lookback_days=self.config.app.lookback_days,
            )
            logger.info("Aktuális kamatadatok: %d sor", len(retail))
        except AkkError as exc:
            errors.append(f"aktuális kamatok: {exc}")
            logger.error("Aktuális kamatadatok lekérése sikertelen: %s", exc)

        outcome.source_errors = errors

        if len(errors) == 2:
            # Teljes leállás: értesítsünk róla (ha kérték), majd jelezzük a hibát.
            self._maybe_notify_error(state, now, errors, dry_run, outcome)
            if not dry_run:
                self._save_state(state)
            raise MonitorError("; ".join(errors))

        if errors:
            logger.warning(
                "Részleges adatlekérési hiba, a másik forrásból dolgozom: %s",
                "; ".join(errors),
            )

        active_offerings = select_active_offerings(offerings, today, now_naive)
        future_offerings = select_future_offerings(
            offerings,
            today,
            self.config.app.announce_horizon_days,
            now_naive,
        )

        active_views = [
            merge_series(offering, match_retail(offering, retail, today))
            for offering in active_offerings
        ]
        future_views = [
            merge_series(offering, match_retail(offering, retail, today))
            for offering in future_offerings
        ]

        retail_active = latest_active_retail(retail, today)
        retail_view = SeriesInfo.from_retail(retail_active) if retail_active else None

        current_view: SeriesInfo | None = None
        if active_views:
            current_view = max(active_views, key=lambda item: (item.start, item.name))
        elif retail_view is not None:
            current_view = retail_view

        outcome.active = current_view
        outcome.upcoming = future_views

        # 3. Első futás: összefoglaló, majd az állapot beállítása.
        if first_run:
            if self.config.app.first_run_notify:
                message = build_first_run(current_view, future_views)
                outcome.messages.append(message)
                if self._dispatch(message, dry_run, outcome):
                    self._mark_first_run(state, current_view, future_views)
                else:
                    logger.warning(
                        "Az első futási összefoglaló nem ment ki; a következő "
                        "futás normál értesítést küld a jelenlegi sorozatról."
                    )
            else:
                self._mark_first_run(state, current_view, future_views)
                logger.info("Első futás: összefoglaló küldése kikapcsolva.")

            state.last_check = now
            if current_view:
                state.last_active = current_view.to_dict()
                state.last_active_at = now
            if not dry_run:
                self._save_state(state)
            return outcome

        # 4. Kényszerített értesítés (teszteléshez).
        forced_names: set[str] = set()
        if force:
            if current_view is not None:
                message = build_start(current_view, today)
                outcome.messages.append(message)
                if self._dispatch(message, dry_run, outcome):
                    state.add_started(current_view.name)
                    state.add_announced(current_view.name)
                    self._schedule_reminder(state, current_view, now)
                forced_names.add(current_view.name)
            elif future_views:
                target = future_views[0]
                message = build_announcement(target)
                outcome.messages.append(message)
                if self._dispatch(message, dry_run, outcome):
                    state.add_announced(target.name)
                forced_names.add(target.name)

        # 5. Új sorozatok kihirdetése (a start előtt).
        if self.config.app.announce_new_offerings:
            for view in future_views:
                if view.name in forced_names or state.was_announced(view.name):
                    continue
                message = build_announcement(view)
                outcome.messages.append(message)
                if self._dispatch(message, dry_run, outcome):
                    state.add_announced(view.name)
        else:
            logger.debug("Az új sorozatok kihirdetéséről szóló értesítés ki van kapcsolva.")

        # 6. Aktuálisan vásárolható sorozatok indulási értesítése.
        if self.config.app.notify_on_start:
            for view in active_views:
                if view.name in forced_names or state.was_started(view.name):
                    continue
                message = build_start(view, today)
                outcome.messages.append(message)
                if self._dispatch(message, dry_run, outcome):
                    state.add_started(view.name)
                    state.add_announced(view.name)
                    self._schedule_reminder(state, view, now)
                    state.last_active = view.to_dict()
                    state.last_active_at = now

            # Ha van ajánlattételi adat az aktív sorozatról, az a mérvadó.
            # A retail forrást csak akkor használjuk, ha onnan nem jött aktív sor.
            if (
                not active_views
                and retail_view is not None
                and retail_view.name not in forced_names
                and not state.was_started(retail_view.name)
            ):
                message = build_start(retail_view, today)
                outcome.messages.append(message)
                if self._dispatch(message, dry_run, outcome):
                    state.add_started(retail_view.name)
                    state.add_announced(retail_view.name)
                    self._schedule_reminder(state, retail_view, now)
                    state.last_active = retail_view.to_dict()
                    state.last_active_at = now
        else:
            logger.debug("Az indulási értesítés ki van kapcsolva.")

        state.last_check = now
        if current_view is not None:
            state.last_active = current_view.to_dict()
            state.last_active_at = now
        if not dry_run:
            self._save_state(state)

        return outcome

    def _process_reminders(
        self,
        state: State,
        now: datetime,
        today: date,
        dry_run: bool,
        outcome: CheckOutcome,
    ) -> None:
        for reminder in list(state.pending_reminders):
            if reminder.series.end is not None and reminder.series.end < today:
                logger.info(
                    "Lejárt sorozat emlékeztetőjét törlöm: %s",
                    reminder.series.name,
                )
                if not dry_run:
                    state.remove_reminder(reminder)
                continue
            if reminder.due_at > now:
                continue
            message = build_reminder(reminder.series, reminder.text)
            outcome.messages.append(message)
            logger.info("Esedékes emlékeztető: %s", reminder.series.name)
            if dry_run:
                continue
            if self._dispatch(message, dry_run, outcome):
                state.remove_reminder(reminder)

    def _schedule_reminder(self, state: State, view: SeriesInfo, now: datetime) -> None:
        if not self.config.reminder.enabled:
            return
        due_at = now + timedelta(hours=self.config.reminder.delay_hours)
        if view.end is not None and due_at.date() > view.end:
            logger.info(
                "Nem ütemezek emlékeztetőt a(z) %s sorozatra, mert a "
                "vásárlási időszak a tervezett emlékeztető előtt lejár.",
                view.name,
            )
            return
        state.add_reminder(
            PendingReminder(
                series=view,
                due_at=due_at,
                text=self.config.reminder.text,
            )
        )
        logger.info(
            "Emlékeztető ütemezve: %s – %s",
            view.name,
            due_at.isoformat(timespec="minutes"),
        )

    def _maybe_notify_error(
        self,
        state: State,
        now: datetime,
        errors: list[str],
        dry_run: bool,
        outcome: CheckOutcome,
    ) -> None:
        if not self.config.app.notify_on_error:
            return
        if state.last_error_notified is not None:
            last = state.last_error_notified
            if last.tzinfo is None:
                last = last.replace(tzinfo=now.tzinfo)
            if now - last < timedelta(hours=24):
                logger.info("Hibaértesítés nyugalmi időben; nem küldök újat.")
                return
        message = build_error("; ".join(errors))
        outcome.messages.append(message)
        if self._dispatch(message, dry_run, outcome) and not dry_run:
            state.last_error_notified = now

    def _dispatch(
        self,
        message: Message,
        dry_run: bool,
        outcome: CheckOutcome,
    ) -> bool:
        if dry_run:
            logger.info("[dry-run] Előkészített értesítés: %s", message.title)
            return True
        result = self.notifiers.send(message)
        outcome.delivery_failures.extend(
            f"{name}: {error}" for name, error in result.failures
        )
        if result.delivered:
            outcome.delivered_messages += 1
            return True
        return False

    def _mark_first_run(
        self,
        state: State,
        current_view: SeriesInfo | None,
        future_views: list[SeriesInfo],
    ) -> None:
        if current_view is not None:
            state.add_started(current_view.name)
            state.add_announced(current_view.name)
        for view in future_views:
            state.add_announced(view.name)

    def _save_state(self, state: State) -> None:
        try:
            self.state_store.save(state)
        except OSError as exc:
            raise MonitorError(f"Az állapotfájl mentése sikertelen: {exc}") from exc
