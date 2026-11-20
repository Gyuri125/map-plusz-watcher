"""Interaktív helyi beállítás Discordhoz és Telegramhoz."""

from __future__ import annotations

import getpass
import re
import shutil
import sys
from pathlib import Path

from .config import ConfigError, find_config, load_config
from .messages import build_test
from .notifiers import NotifierManager, build_notifiers
from .telegram_util import TelegramUtilError, extract_chats, fetch_updates

ENV_KEYS = ("DISCORD_WEBHOOK_URL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
_SECTION = re.compile(r"^\[([^\]]+)\]\s*$")


def _validate_webhook(value: str) -> bool:
    return value.startswith("https://") and "/api/webhooks/" in value


def _validate_bot_token(value: str) -> bool:
    return bool(re.fullmatch(r"\d+:[A-Za-z0-9_-]+", value))


def _update_env_file(path: Path, values: dict[str, str]) -> None:
    """Meglévő .env frissítése a megadott kulcsokkal, a többit megtartva."""
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    remaining = dict(values)
    updated: list[str] = []
    for line in lines:
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=", line)
        if match and match.group(1) in remaining:
            key = match.group(1)
            updated.append(f"{key}={remaining.pop(key)}")
        else:
            updated.append(line)
    for key, value in remaining.items():
        if updated and updated[-1].strip():
            updated.append("")
        updated.append(f"{key}={value}")
    path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def _set_section_enabled(text: str, section: str, enabled: bool) -> str:
    """Egy TOML szakasz enabled kulcsának beállítása, a többi érintetlenül."""
    lines = text.splitlines()
    header = f"[{section}]"
    start = next((i for i, line in enumerate(lines) if line.strip() == header), None)
    value = "true" if enabled else "false"
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([header, f"enabled = {value}"])
        return "\n".join(lines) + "\n"

    end = len(lines)
    for i in range(start + 1, len(lines)):
        if _SECTION.match(lines[i].strip()):
            end = i
            break
    for i in range(start + 1, end):
        if re.match(r"^\s*enabled\s*=", lines[i]):
            lines[i] = f"enabled = {value}"
            return "\n".join(lines) + "\n"
    lines.insert(start + 1, f"enabled = {value}")
    return "\n".join(lines) + "\n"


def _ask_yes(prompt: str, default: bool = True) -> bool:
    suffix = " [I/n] " if default else " [i/N] "
    answer = input(prompt + suffix).strip().lower()
    if not answer:
        return default
    return answer in {"i", "igen", "y", "yes"}


def _copy_example(target: Path) -> None:
    example = Path(__file__).resolve().parent.parent / "config.example.toml"
    if not example.exists():
        example = Path.cwd() / "config.example.toml"
    if not example.exists():
        raise ConfigError("Nem találom a config.example.toml mintát.")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(example, target)


def run_setup(config_path: str | None = None) -> int:
    if not sys.stdin.isatty():
        print("A setup parancs interaktív terminalt igényel.", file=sys.stderr)
        return 2

    if config_path:
        path = Path(config_path).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
    else:
        try:
            path = find_config(None)
        except ConfigError:
            path = (Path.cwd() / "config.toml").resolve()

    if not path.exists():
        print(f"Nem találom a configot, létrehozom a mintából: {path}")
        try:
            _copy_example(path)
        except (OSError, ConfigError) as exc:
            print(f"Nem sikerült létrehozni a configot: {exc}", file=sys.stderr)
            return 1

    print()
    print("MÁP+ Watcher – helyi beállítás")
    print("=" * 50)
    print(f"Config: {path}")
    print("A titkok a config melletti .env fájlba kerülnek, ami nincs a repóban.")
    print()

    values: dict[str, str] = {}
    enable_discord = False
    enable_telegram = False

    if _ask_yes("Discord értesítés bekapcsolása?", True):
        for _ in range(3):
            webhook = getpass.getpass("Discord webhook URL (nem látszik): ").strip()
            if _validate_webhook(webhook):
                values["DISCORD_WEBHOOK_URL"] = webhook
                enable_discord = True
                break
            print("Ez nem tűnik Discord webhook URL-nek (https://.../api/webhooks/...).")
        if not enable_discord:
            print("A Discord beállítása kimarad.")

    if _ask_yes("Telegram értesítés bekapcsolása?", True):
        for _ in range(3):
            token = getpass.getpass("Telegram bot token (nem látszik): ").strip()
            if _validate_bot_token(token):
                values["TELEGRAM_BOT_TOKEN"] = token
                break
            print("A token formátuma nem megfelelő (pl. 123456:ABC...).")
        if "TELEGRAM_BOT_TOKEN" in values:
            detected: str = ""
            try:
                chats = extract_chats(fetch_updates(values["TELEGRAM_BOT_TOKEN"]))
            except TelegramUtilError:
                chats = []
            if chats:
                print("Talált Telegram chat-ek:")
                for chat in chats:
                    print(f"  ID: {chat['id']}  |  {chat['title']}  ({chat['type']})")
                target = next(
                    (
                        chat
                        for chat in chats
                        if chat["type"] in {"group", "supergroup", "channel"}
                    ),
                    chats[0],
                )
                if _ask_yes(
                    f"Használjam ezt a chat_id-t: {target['id']} ({target['title']})?",
                    True,
                ):
                    detected = str(target["id"])
            if detected:
                values["TELEGRAM_CHAT_ID"] = detected
                enable_telegram = True
            else:
                print(
                    "Nem találtam automatikusan chatet. Írj a csoportban "
                    "a botnak, vagy használd a @getidsbot botot."
                )
                chat_id = input("Telegram chat_id: ").strip()
                if chat_id:
                    values["TELEGRAM_CHAT_ID"] = chat_id
                    enable_telegram = True
                else:
                    print("A chat_id üres, a Telegram beállítása kimarad.")
        else:
            print("A Telegram beállítása kimarad.")

    if not values:
        print("Nem adtál meg új csatornát; a beállítás nem változott.")
        return 0

    try:
        env_path = path.parent / ".env"
        _update_env_file(env_path, values)
        text = path.read_text(encoding="utf-8")
        if enable_discord:
            text = _set_section_enabled(text, "notifiers.discord", True)
        if enable_telegram:
            text = _set_section_enabled(text, "notifiers.telegram", True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        print(f"A beállítások mentése sikertelen: {exc}", file=sys.stderr)
        return 1

    print()
    print(f"Elkészült: {env_path}")
    print(f"Config frissítve: {path}")
    print("A .env fájlt a .gitignore kizárja, nem kerül a repóba.")
    print()

    if _ask_yes("Küldjünk most tesztértesítést?", True):
        try:
            config = load_config(path)
            manager = NotifierManager(build_notifiers(config))
            print("Tesztértesítés küldése: " + ", ".join(manager.names))
            result = manager.send(build_test())
            for name in result.successes:
                print(f"  [OK]   {name}")
            for name, error in result.failures:
                print(f"  [HIBA] {name}: {error}")
            if not result.ok:
                print("A hibás csatornát ellenőrizd, majd futtasd újra: setup")
        except ConfigError as exc:
            print(f"A config ellenőrzése sikertelen: {exc}", file=sys.stderr)
            return 1

    print()
    print("GitHub Actions secretök (Settings > Secrets and variables > Actions):")
    print("  DISCORD_WEBHOOK_URL")
    print("  TELEGRAM_BOT_TOKEN")
    print("  TELEGRAM_CHAT_ID")
    print("A helyi próbához: python -m allampapir_ertesito check --dry-run")
    return 0
