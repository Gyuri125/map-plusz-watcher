"""Parancssori felület."""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import shutil
import sys
import time
from pathlib import Path

from . import __version__
from .akk import AkkClient, AkkError
from .config import Config, ConfigError, load_config
from .dashboard import DashboardError, build_data, write_dashboard
from .messages import build_test
from .models import CheckOutcome, Offering, RetailSeries, SeriesInfo
from .monitor import (
    Monitor,
    MonitorError,
    SystemClock,
    latest_active_retail,
    match_retail,
    merge_series,
    select_active_offerings,
    select_future_offerings,
)
from .notifiers import NotifierManager, build_notifiers
from .setup_wizard import run_setup
from .state import StateStore
from .summary import write_github_summary
from .util import (
    format_date_hu,
    format_datetime_hu,
    format_percent,
    format_rate_range,
    parse_date,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_EXAMPLE = PROJECT_ROOT / "config.example.toml"
LOGGER_NAME = "allampapir"


def setup_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            pass


def setup_logging(config: Config, verbose: bool) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if config.app.log_file is not None:
        try:
            config.app.log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                config.app.log_file,
                maxBytes=1_000_000,
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError as exc:
            logger.warning("A naplófájl nem nyitható meg (%s): %s", config.app.log_file, exc)


def build_runtime(config: Config) -> tuple[Monitor, NotifierManager]:
    client = AkkClient(timeout=config.app.http_timeout_seconds)
    manager = NotifierManager(build_notifiers(config))
    store = StateStore(config.app.state_file)
    monitor = Monitor(config, client, manager, store)
    return monitor, manager


def run_check(config: Config, dry_run: bool = False, force: bool = False) -> int:
    logger = logging.getLogger(LOGGER_NAME)
    monitor, _ = build_runtime(config)
    try:
        outcome = monitor.check(dry_run=dry_run, force=force)
    except MonitorError as exc:
        logger.error("%s", exc)
        return 1

    if dry_run:
        print_dry_run(outcome)
    else:
        write_github_summary(outcome, config)

    if outcome.source_errors:
        logger.warning("Adatforrás hibák: %s", "; ".join(outcome.source_errors))
    if outcome.delivery_failures:
        logger.warning("Kézbesítési hibák: %s", "; ".join(outcome.delivery_failures))

    if not outcome.messages:
        logger.info("Nincs új értesítés.")
    else:
        logger.info(
            "Értesítések: %d előkészítve, %d sikeresen elküldve.",
            len(outcome.messages),
            outcome.delivered_messages,
        )

    if outcome.messages and not dry_run and outcome.delivered_messages == 0:
        return 1
    return 0


def print_dry_run(outcome: CheckOutcome) -> None:
    if not outcome.messages:
        print("\nDry-run: nincs új értesítés.\n")
        return
    print("\nDRY-RUN – az alábbi értesítések mennének ki:")
    for message in outcome.messages:
        print()
        print("=" * 72)
        print(message.title)
        print("=" * 72)
        print(message.body)
    print("\n(Az állapot nem változott, értesítés nem ment ki.)\n")


def run_test(config: Config) -> int:
    manager = NotifierManager(build_notifiers(config))
    if not manager.notifiers:
        print("Nincs bekapcsolt értesítési csatorna.", file=sys.stderr)
        return 2
    print(f"Tesztértesítés küldése ezekre a csatornákra: {', '.join(manager.names)}")
    result = manager.send(build_test())
    for name in result.successes:
        print(f"  [OK]   {name}")
    for name, error in result.failures:
        print(f"  [HIBA] {name}: {error}")
    return 0 if result.ok else 1


def _describe_series(series: SeriesInfo) -> str:
    parts = [f"{series.name}"]
    parts.append(
        f"{format_date_hu(series.start)} – "
        f"{format_date_hu(series.end) if series.end else 'visszavonásig'}"
    )
    rate = format_rate_range(series.rate)
    if rate:
        parts.append(f"kamat: {rate}")
    if series.ehm:
        ehm = format_percent(series.ehm)
        if ehm:
            parts.append(f"EHM: {ehm}")
    if series.isin:
        parts.append(f"ISIN: {series.isin}")
    return " | ".join(parts)


def run_status(config: Config, offline: bool) -> int:
    print("MÁP+ értesítő – állapot")
    print("=" * 72)
    print(f"Konfiguráció: {config.path}")
    print(f"Állapotfájl: {config.app.state_file}")
    print(f"Napló: {config.app.log_file or '(nincs fájlnapló)'}")
    print(f"Csatornák: {', '.join(config.enabled_notifier_names)}")
    print(f"Időzóna: {config.app.timezone}")

    state = StateStore(config.app.state_file).load()
    print()
    print("Állapot:")
    print(f"  Utolsó ellenőrzés: {format_datetime_hu(state.last_check) or 'még nem futott'}")
    if state.last_active:
        name = state.last_active.get("name", "?")
        start = parse_date(state.last_active.get("start"))
        end = parse_date(state.last_active.get("end"))
        date_text = (
            f"{format_date_hu(start)} – "
            f"{format_date_hu(end) if end else 'visszavonásig'}"
        )
        print(f"  Utolsó aktív sorozat: {name} ({date_text})")
    else:
        print("  Utolsó aktív sorozat: nincs feljegyzés")
    if state.pending_reminders:
        print("  Emlékeztetők:")
        for reminder in state.pending_reminders:
            print(
                f"    - {reminder.series.name}: "
                f"{format_datetime_hu(reminder.due_at)}"
            )
    else:
        print("  Emlékeztetők: nincs")
    if state.last_error_notified:
        print(f"  Utolsó hibaértesítés: {format_datetime_hu(state.last_error_notified)}")

    if offline:
        return 0

    print()
    print("Élő adatok:")
    client = AkkClient(timeout=config.app.http_timeout_seconds)
    clock = SystemClock(config.app.timezone)
    now = clock.now()
    today = now.date()
    now_naive = now.replace(tzinfo=None) if now.tzinfo else now
    offerings: list[Offering] = []
    retail: list[RetailSeries] = []
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
        retail = client.fetch_retail(
            today,
            lookback_days=config.app.lookback_days,
        )
    except AkkError as exc:
        errors.append(f"aktuális kamatok: {exc}")

    if errors:
        for error in errors:
            print(f"  [HIBA] {error}")
        return 1

    active = select_active_offerings(offerings, today, now_naive)
    future = select_future_offerings(
        offerings,
        today,
        config.app.announce_horizon_days,
        now_naive,
    )
    if active:
        for offering in active:
            print(f"  Kapható: {_describe_series(merge_series(offering, match_retail(offering, retail, today)))}")
    else:
        retail_active = latest_active_retail(retail, today)
        if retail_active:
            print(f"  Kapható (retail adatból): {_describe_series(SeriesInfo.from_retail(retail_active))}")
        else:
            print("  Kapható: jelenleg nincs")

    if future:
        for offering in future:
            print(f"  Hamarosan: {_describe_series(merge_series(offering, match_retail(offering, retail, today)))}")
    else:
        print("  Hamarosan: nincs kihirdetett sorozat a figyelt időszakban")
    return 0


def run_dashboard(config: Config, output: str) -> int:
    logger = logging.getLogger(LOGGER_NAME)
    client = AkkClient(timeout=config.app.http_timeout_seconds)
    try:
        data = build_data(client, config)
    except DashboardError as exc:
        logger.error("A dashboardhoz nem sikerült adatot szerezni: %s", exc)
        return 1
    if data.source_errors:
        logger.warning("Részleges adatlekérési hiba: %s", "; ".join(data.source_errors))
    output_dir = Path(output)
    if not output_dir.is_absolute():
        output_dir = (Path.cwd() / output_dir).resolve()
    try:
        index_path = write_dashboard(data, config, output_dir)
    except OSError as exc:
        logger.error("A dashboard írása sikertelen: %s", exc)
        return 1
    logger.info("Dashboard elkészült: %s", index_path)
    print(f"Dashboard: {index_path}")
    return 0


def run_watch(config: Config, interval_minutes: int) -> int:
    logger = logging.getLogger(LOGGER_NAME)
    if interval_minutes < 1:
        print("Az intervallum legalább 1 perc legyen.", file=sys.stderr)
        return 2
    logger.info("Figyelő indult, %d percenként ellenőrzök. Leállítás: Ctrl+C.", interval_minutes)
    try:
        while True:
            started = time.monotonic()
            try:
                code = run_check(config)
            except Exception:
                logger.exception("A figyelési ciklus váratlan hibával leállt.")
                code = 1
            logger.info("Ciklus kész (exit=%d).", code)
            sleep_seconds = max(0.0, interval_minutes * 60 - (time.monotonic() - started))
            deadline = time.monotonic() + sleep_seconds
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(remaining, 1.0))
    except KeyboardInterrupt:
        logger.info("Figyelő leállítva.")
        return 0


def run_init(args: argparse.Namespace) -> int:
    target = Path(args.config).expanduser() if args.config else Path.cwd() / "config.toml"
    if not target.is_absolute():
        target = (Path.cwd() / target).resolve()
    source = CONFIG_EXAMPLE
    if not source.exists():
        source = Path.cwd() / "config.example.toml"
    if not source.exists():
        print(
            f"Nem találom a config.example.toml mintát. Keresett helyek:\n"
            f"  {CONFIG_EXAMPLE}\n  {Path.cwd() / 'config.example.toml'}",
            file=sys.stderr,
        )
        return 1
    if target.exists() and not args.force:
        print(f"A(z) {target} már létezik. Felülíráshoz használd a --force kapcsolót.", file=sys.stderr)
        return 2
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    except OSError as exc:
        print(f"Nem sikerült a config.toml létrehozása: {exc}", file=sys.stderr)
        return 1
    print(f"Elkészült: {target}")
    print()
    print("Következő lépések:")
    print(f"  1. Nyisd meg és állítsd be a csatornát: {target}")
    print("     (A legegyszerűbb mobilértesítés az ntfy; e-mail és Telegram is van.)")
    print(f'  2. python -m allampapir_ertesito test --config "{target}"')
    print(f'  3. python -m allampapir_ertesito check --dry-run --config "{target}"')
    print(f'  4. python -m allampapir_ertesito check --config "{target}"')
    print("  5. Ütemezés: scripts\\register_task.ps1")
    print()
    print("A titkokat (jelszó, bot token) érdemes környezeti változóban tárolni,")
    print("a config.toml-ban csak ${VALTOZO_NEV} hivatkozás legyen.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="allampapir-ertesito",
        description="MÁP+ állampapír sorozatok figyelése és értesítése.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--config", help="A config.toml útvonala.")
        sub.add_argument("--verbose", action="store_true", help="Részletes naplózás.")

    check = subparsers.add_parser("check", help="Egyszeri ellenőrzés.")
    add_common(check)
    check.add_argument(
        "--dry-run",
        action="store_true",
        help="Csak kiírja, milyen értesítés menne ki; állapotot nem módosít.",
    )
    check.add_argument(
        "--force",
        action="store_true",
        help="A jelenlegi/legközelebbi sorozatról akkor is értesít, ha már megtörtént.",
    )

    watch = subparsers.add_parser("watch", help="Folyamatos figyelés adott időközzel.")
    add_common(watch)
    watch.add_argument(
        "--interval-minutes",
        type=int,
        default=60,
        help="Ellenőrzések között eltelt percek (alapértelmezés: 60).",
    )

    test = subparsers.add_parser("test", help="Tesztértesítés küldése a beállított csatornákra.")
    add_common(test)

    status = subparsers.add_parser("status", help="Beállítások és állapot megjelenítése.")
    add_common(status)
    status.add_argument(
        "--offline",
        action="store_true",
        help="Ne kérje le az élő adatokat, csak a helyi állapotot mutassa.",
    )

    dashboard = subparsers.add_parser(
        "dashboard",
        help="Statikus dashboard és naptárfájl generálása.",
    )
    add_common(dashboard)
    dashboard.add_argument(
        "--output",
        default="site",
        help="Kimeneti mappa (alapértelmezés: site).",
    )

    setup = subparsers.add_parser(
        "setup",
        help="Interaktív helyi beállítás Discordhoz és Telegramhoz.",
    )
    add_common(setup)

    init = subparsers.add_parser("init", help="config.toml létrehozása a mintából.")
    init.add_argument("--config", help="A létrehozandó config.toml útvonala.")
    init.add_argument("--force", action="store_true", help="Meglévő fájl felülírása.")
    return parser


def main(argv: list[str] | None = None) -> int:
    setup_console_encoding()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        return run_init(args)
    if args.command == "setup":
        return run_setup(args.config)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Konfigurációs hiba: {exc}", file=sys.stderr)
        return 2

    setup_logging(config, args.verbose)
    logger = logging.getLogger(LOGGER_NAME)

    try:
        if args.command == "check":
            return run_check(config, dry_run=args.dry_run, force=args.force)
        if args.command == "watch":
            return run_watch(config, args.interval_minutes)
        if args.command == "test":
            return run_test(config)
        if args.command == "status":
            return run_status(config, offline=args.offline)
        if args.command == "dashboard":
            return run_dashboard(config, args.output)
        parser.error(f"Ismeretlen parancs: {args.command}")
        return 2
    except ConfigError as exc:
        logger.error("Konfigurációs hiba: %s", exc)
        return 2
    except KeyboardInterrupt:
        print("\nLeállítva.", file=sys.stderr)
        return 130
    except Exception:
        logger.exception("Váratlan hiba történt.")
        return 1
