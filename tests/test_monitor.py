from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from allampapir_ertesito.akk import AkkError
from allampapir_ertesito.config import ReminderSettings
from allampapir_ertesito.models import Offering, RetailSeries
from allampapir_ertesito.monitor import Monitor, MonitorError
from allampapir_ertesito.notifiers.base import NotifierManager
from allampapir_ertesito.state import State, StateStore
from tests.helpers import (
    FakeClient,
    FakeClock,
    FakeNotifier,
    make_config,
    make_offering,
    make_retail,
    utc,
)


class MonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.config = make_config(self.directory)
        self.notifier = FakeNotifier()
        self.manager = NotifierManager([self.notifier])
        self.store = StateStore(self.config.app.state_file)

    def _monitor(self, client: FakeClient, now: datetime) -> Monitor:
        return Monitor(
            self.config,
            client,  # type: ignore[arg-type]
            self.manager,
            self.store,
            clock=FakeClock(now),
        )

    @staticmethod
    def _m6() -> Offering:
        return make_offering(
            "2031/M6",
            date(2026, 10, 1),
            date(2026, 12, 31),
            published=datetime(2026, 9, 25, 13, 30),
        )

    @staticmethod
    def _retail_m6() -> RetailSeries:
        return make_retail("2031/M6", date(2026, 10, 1), None)

    def test_first_run_sends_summary_and_does_not_repeat(self) -> None:
        client = FakeClient([self._m6()], [self._retail_m6()])
        monitor = self._monitor(client, utc(2026, 11, 19))
        outcome = monitor.check()
        self.assertTrue(outcome.first_run)
        self.assertEqual(len(outcome.messages), 1)
        self.assertEqual(outcome.messages[0].event, "first_run")
        self.assertIn("2031/M6", outcome.messages[0].body)
        self.assertEqual(outcome.delivered_messages, 1)
        self.assertTrue(self.config.app.state_file.exists())

        again = monitor.check()
        self.assertFalse(again.first_run)
        self.assertEqual(again.messages, [])

    def test_announcement_then_start_and_no_duplicates(self) -> None:
        m6 = self._m6()
        retail_m6 = self._retail_m6()
        m7 = make_offering(
            "2031/M7",
            date(2027, 1, 4),
            date(2027, 3, 31),
            published=datetime(2026, 12, 28, 13, 30),
        )
        client = FakeClient([m6], [retail_m6])
        clock = FakeClock(utc(2026, 12, 1))
        monitor = Monitor(
            self.config,
            client,  # type: ignore[arg-type]
            self.manager,
            self.store,
            clock=clock,
        )
        first = monitor.check()
        self.assertEqual(first.messages[0].event, "first_run")

        client.offerings = [m6, m7]
        clock.current = utc(2026, 12, 28, 12, 0)
        before_publication = monitor.check()
        self.assertEqual(before_publication.messages, [])

        clock.current = utc(2026, 12, 28, 14, 0)
        announcement = monitor.check()
        self.assertEqual([item.event for item in announcement.messages], ["announcement"])
        self.assertIn("2031/M7", announcement.messages[0].title)
        self.assertIn("2027. 01. 04.", announcement.messages[0].body)

        duplicate = monitor.check()
        self.assertEqual(duplicate.messages, [])

        client.offerings = [m7]
        client.retail = [retail_m6]
        clock.current = utc(2027, 1, 4, 9, 0)
        start = monitor.check()
        self.assertEqual([item.event for item in start.messages], ["start"])
        self.assertIn("Ma válik vásárolhatóvá", start.messages[0].title)

        duplicate_start = monitor.check()
        self.assertEqual(duplicate_start.messages, [])

    def test_start_alert_for_already_active_series_after_silent_bootstrap(self) -> None:
        self.store.save(State(last_check=utc(2026, 11, 18)))
        client = FakeClient([self._m6()], [self._retail_m6()])
        monitor = self._monitor(client, utc(2026, 11, 19))
        outcome = monitor.check()
        self.assertEqual([item.event for item in outcome.messages], ["start"])
        self.assertIn("2031/M6", outcome.messages[0].title)

    def test_retail_fallback_when_offering_feed_is_empty(self) -> None:
        self.store.save(State(last_check=utc(2026, 11, 18)))
        client = FakeClient([], [self._retail_m6()])
        monitor = self._monitor(client, utc(2026, 11, 19))
        outcome = monitor.check()
        self.assertEqual([item.event for item in outcome.messages], ["start"])
        self.assertIn("2031/M6", outcome.messages[0].title)

    def test_reminder_is_scheduled_and_sent(self) -> None:
        self.config.reminder = ReminderSettings(
            enabled=True,
            delay_hours=24,
            text="Fizesd be a vételárat.",
        )
        m6 = self._m6()
        retail_m6 = self._retail_m6()
        m7 = make_offering(
            "2031/M7",
            date(2027, 1, 4),
            date(2027, 3, 31),
            published=datetime(2026, 12, 28, 13, 30),
        )
        client = FakeClient([m6], [retail_m6])
        clock = FakeClock(utc(2026, 12, 30))
        monitor = Monitor(
            self.config,
            client,  # type: ignore[arg-type]
            self.manager,
            self.store,
            clock=clock,
        )
        monitor.check()

        client.offerings = [m7]
        announcement = monitor.check()
        self.assertEqual([item.event for item in announcement.messages], ["announcement"])

        clock.current = utc(2027, 1, 4, 9, 0)
        start = monitor.check()
        self.assertEqual([item.event for item in start.messages], ["start"])
        state = self.store.load()
        self.assertEqual(len(state.pending_reminders), 1)

        clock.current = utc(2027, 1, 5, 10, 0)
        reminder = monitor.check()
        self.assertEqual([item.event for item in reminder.messages], ["reminder"])
        self.assertIn("Fizesd be a vételárat.", reminder.messages[0].body)
        self.assertEqual(self.store.load().pending_reminders, [])

        clock.current = utc(2027, 1, 5, 11, 0)
        duplicate = monitor.check()
        self.assertEqual(duplicate.messages, [])

    def test_dry_run_does_not_write_state_or_send(self) -> None:
        client = FakeClient([self._m6()], [self._retail_m6()])
        monitor = self._monitor(client, utc(2026, 11, 19))
        outcome = monitor.check(dry_run=True)
        self.assertEqual(len(outcome.messages), 1)
        self.assertFalse(self.config.app.state_file.exists())
        self.assertEqual(self.notifier.messages, [])

    def test_partial_source_error_still_works(self) -> None:
        client = FakeClient(
            [self._m6()],
            retail_error=AkkError("retail hiba"),
        )
        monitor = self._monitor(client, utc(2026, 11, 19))
        outcome = monitor.check()
        self.assertEqual(len(outcome.source_errors), 1)
        self.assertEqual(len(outcome.messages), 1)
        self.assertEqual(outcome.messages[0].event, "first_run")

    def test_total_source_error_raises_and_keeps_first_run(self) -> None:
        client = FakeClient(
            offerings_error=AkkError("offering hiba"),
            retail_error=AkkError("retail hiba"),
        )
        monitor = self._monitor(client, utc(2026, 11, 19))
        with self.assertRaises(MonitorError):
            monitor.check()
        state = self.store.load()
        self.assertTrue(state.is_empty)
        self.assertIsNone(state.last_check)

    def test_force_resends_current_series(self) -> None:
        client = FakeClient([self._m6()], [self._retail_m6()])
        monitor = self._monitor(client, utc(2026, 11, 19))
        monitor.check()
        self.notifier.messages.clear()
        outcome = monitor.check(force=True)
        self.assertEqual([item.event for item in outcome.messages], ["start"])


if __name__ == "__main__":
    unittest.main()
