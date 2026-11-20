"""TOML konfiguráció betöltése és ellenőrzése."""

from __future__ import annotations

import logging
import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("allampapir.config")
_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_VALID_NTFY_PRIORITIES = {"min", "low", "default", "high", "urgent"}


class ConfigError(RuntimeError):
    """Hibás vagy hiányzó konfiguráció."""


@dataclass
class AppSettings:
    first_run_notify: bool = True
    announce_new_offerings: bool = True
    notify_on_start: bool = True
    ending_soon_days: int = 14
    notify_on_error: bool = False
    state_file: Path = Path("state.json")
    log_file: Path | None = Path("logs/allampapir.log")
    timezone: str = "Europe/Budapest"
    lookback_days: int = 730
    announce_horizon_days: int = 120
    http_timeout_seconds: int = 30
    public_url: str = ""


@dataclass
class ConsoleSettings:
    enabled: bool = True


@dataclass
class NtfySettings:
    enabled: bool = False
    url: str = "https://ntfy.sh"
    topic: str = ""
    priority: str = "high"
    tags: tuple[str, ...] = ("moneybag",)
    click_url: str = "https://webkincstar.allamkincstar.gov.hu/"
    token: str = ""


@dataclass
class EmailSettings:
    enabled: bool = False
    host: str = ""
    port: int = 587
    starttls: bool = True
    ssl: bool = False
    username: str = ""
    password: str = ""
    from_addr: str = ""
    to: tuple[str, ...] = ()
    timeout: int = 30


@dataclass
class TelegramSettings:
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""
    message_thread_id: int = 0


@dataclass
class DiscordSettings:
    enabled: bool = False
    webhook_url: str = ""
    username: str = "MÁP+ értesítő"
    avatar_url: str = ""


@dataclass
class WindowsSettings:
    enabled: bool = False


@dataclass
class WebhookSettings:
    enabled: bool = False
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class ReminderSettings:
    enabled: bool = False
    delay_hours: int = 24
    text: str = (
        "Ne feledd: az új MÁP+ sorozat megvásárlásához a vételárat is "
        "rendezned kell."
    )


@dataclass
class Config:
    path: Path
    app: AppSettings
    console: ConsoleSettings
    ntfy: NtfySettings
    email: EmailSettings
    telegram: TelegramSettings
    discord: DiscordSettings
    windows: WindowsSettings
    webhook: WebhookSettings
    reminder: ReminderSettings

    @property
    def base_dir(self) -> Path:
        return self.path.parent

    @property
    def enabled_notifier_names(self) -> list[str]:
        names: list[str] = []
        if self.console.enabled:
            names.append("console")
        if self.email.enabled:
            names.append("email")
        if self.telegram.enabled:
            names.append("telegram")
        if self.discord.enabled:
            names.append("discord")
        if self.ntfy.enabled:
            names.append("ntfy")
        if self.windows.enabled:
            names.append("windows")
        if self.webhook.enabled:
            names.append("webhook")
        return names


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            return os.environ.get(match.group(1), "")

        # Csak a saját ${VALTOZO} helyőrzőinket cseréljük. Az os.path.expandvars
        # veszélyes lenne, mert a behelyettesített titokban lévő $ karaktereket
        # is újra tudná értelmezni.
        return _PLACEHOLDER.sub(replace, value)
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    return value


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"Nem találom a konfigurációs fájlt: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Hibás TOML a(z) {path} fájlban: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Nem tudom olvasni a(z) {path} fájlt: {exc}") from exc
    return _expand_env(raw)


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"A(z) [{name}] szakasz nem táblázat.")
    return value


def _resolve_path(base: Path, value: str | os.PathLike[str] | None) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    path = Path(os.path.expanduser(text))
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "igen", "yes", "on"}:
            return True
        if lowered in {"0", "false", "nem", "no", "off"}:
            return False
    raise ConfigError(f"Logikai értéket vártam, ezt kaptam: {value!r}")


def _as_int(value: Any, default: int, name: str) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"A(z) {name} egész szám kell legyen: {value!r}") from exc


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _as_str_list(value: Any, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    raise ConfigError(f"Szöveglistát vártam, ezt kaptam: {value!r}")


def _load_dotenv(base: Path) -> None:
    """Egyszerű .env betöltés helyi futtatáshoz.

    A már beállított környezeti változókat nem írja felül, így a GitHub
    Actions secretjei és a shellből kapott értékek elsőbbséget élveznek.
    """
    candidates = [base / ".env"]
    cwd_env = Path.cwd() / ".env"
    if cwd_env.resolve() != candidates[0].resolve():
        candidates.append(cwd_env)

    for path in candidates:
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except OSError as exc:
            raise ConfigError(f"Nem tudom olvasni a(z) {path} fájlt: {exc}") from exc
        for line in lines:
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            if text.lower().startswith("export "):
                text = text[7:].strip()
            if "=" not in text:
                continue
            key, value = text.split("=", 1)
            key = key.strip()
            if not key or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ.setdefault(key, value)
        logger.debug("Helyi .env betöltve: %s", path)


def find_config(explicit: str | os.PathLike[str] | None = None) -> Path:
    """A konfiguráció keresése: --config, környezeti változó, munkakönyvtár, APPDATA."""
    if explicit:
        path = Path(os.path.expanduser(str(explicit)))
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()

    env_path = os.environ.get("ALLAMPAPIR_CONFIG")
    if env_path:
        return Path(os.path.expanduser(env_path)).resolve()

    local = (Path.cwd() / "config.toml").resolve()
    if local.exists():
        return local

    appdata = os.environ.get("APPDATA")
    if appdata:
        candidate = Path(appdata) / "AllampapirErtesito" / "config.toml"
        if candidate.exists():
            return candidate

    raise ConfigError(
        "Nem találom a config.toml fájlt. Hozd létre a mintából:\n"
        "  python -m allampapir_ertesito init\n"
        "vagy add meg az útvonalat: --config C:\\utvonal\\config.toml"
    )


def load_config(path: str | os.PathLike[str] | None = None) -> Config:
    config_path = find_config(path)
    _load_dotenv(config_path.parent)
    raw = _read_toml(config_path)
    base = config_path.parent

    app_raw = _section(raw, "app")
    console_raw = _section(raw, "notifiers").get("console", {}) or {}
    ntfy_raw = _section(raw, "notifiers").get("ntfy", {}) or {}
    email_raw = _section(raw, "notifiers").get("email", {}) or {}
    telegram_raw = _section(raw, "notifiers").get("telegram", {}) or {}
    discord_raw = _section(raw, "notifiers").get("discord", {}) or {}
    windows_raw = _section(raw, "notifiers").get("windows", {}) or {}
    webhook_raw = _section(raw, "notifiers").get("webhook", {}) or {}
    reminder_raw = _section(raw, "reminder")

    if not isinstance(console_raw, dict):
        raise ConfigError("[notifiers.console] nem táblázat.")
    if not isinstance(ntfy_raw, dict):
        raise ConfigError("[notifiers.ntfy] nem táblázat.")
    if not isinstance(email_raw, dict):
        raise ConfigError("[notifiers.email] nem táblázat.")
    if not isinstance(telegram_raw, dict):
        raise ConfigError("[notifiers.telegram] nem táblázat.")
    if not isinstance(discord_raw, dict):
        raise ConfigError("[notifiers.discord] nem táblázat.")
    if not isinstance(windows_raw, dict):
        raise ConfigError("[notifiers.windows] nem táblázat.")
    if not isinstance(webhook_raw, dict):
        raise ConfigError("[notifiers.webhook] nem táblázat.")

    app = AppSettings(
        first_run_notify=_as_bool(app_raw.get("first_run_notify"), True),
        announce_new_offerings=_as_bool(app_raw.get("announce_new_offerings"), True),
        notify_on_start=_as_bool(app_raw.get("notify_on_start"), True),
        ending_soon_days=_as_int(
            app_raw.get("ending_soon_days"), 14, "app.ending_soon_days"
        ),
        notify_on_error=_as_bool(app_raw.get("notify_on_error"), False),
        state_file=_resolve_path(base, app_raw.get("state_file", "state.json")) or (base / "state.json"),
        log_file=_resolve_path(base, app_raw.get("log_file", "logs/allampapir.log")),
        timezone=_as_str(app_raw.get("timezone"), "Europe/Budapest"),
        lookback_days=_as_int(app_raw.get("lookback_days"), 730, "app.lookback_days"),
        announce_horizon_days=_as_int(
            app_raw.get("announce_horizon_days"), 120, "app.announce_horizon_days"
        ),
        http_timeout_seconds=_as_int(
            app_raw.get("http_timeout_seconds"), 30, "app.http_timeout_seconds"
        ),
        public_url=_as_str(app_raw.get("public_url"), "").rstrip("/"),
    )

    console = ConsoleSettings(
        enabled=_as_bool(console_raw.get("enabled"), True),
    )

    tags = _as_str_list(ntfy_raw.get("tags"), ("moneybag",))
    ntfy = NtfySettings(
        enabled=_as_bool(ntfy_raw.get("enabled"), False),
        url=_as_str(ntfy_raw.get("url"), "https://ntfy.sh"),
        topic=_as_str(ntfy_raw.get("topic"), ""),
        priority=_as_str(ntfy_raw.get("priority"), "high").lower(),
        tags=tags,
        click_url=_as_str(
            ntfy_raw.get("click_url"), "https://webkincstar.allamkincstar.gov.hu/"
        ),
        token=_as_str(ntfy_raw.get("token"), ""),
    )

    email = EmailSettings(
        enabled=_as_bool(email_raw.get("enabled"), False),
        host=_as_str(email_raw.get("host"), ""),
        port=_as_int(email_raw.get("port"), 587, "notifiers.email.port"),
        starttls=_as_bool(email_raw.get("starttls"), True),
        ssl=_as_bool(email_raw.get("ssl"), False),
        username=_as_str(email_raw.get("username"), ""),
        password=_as_str(email_raw.get("password"), ""),
        from_addr=_as_str(email_raw.get("from"), ""),
        to=_as_str_list(email_raw.get("to"), ()),
        timeout=app.http_timeout_seconds,
    )

    telegram = TelegramSettings(
        enabled=_as_bool(telegram_raw.get("enabled"), False),
        bot_token=_as_str(telegram_raw.get("bot_token"), ""),
        chat_id=_as_str(telegram_raw.get("chat_id"), ""),
        message_thread_id=_as_int(
            telegram_raw.get("message_thread_id"), 0, "notifiers.telegram.message_thread_id"
        ),
    )

    discord = DiscordSettings(
        enabled=_as_bool(discord_raw.get("enabled"), False),
        webhook_url=_as_str(discord_raw.get("webhook_url"), ""),
        username=_as_str(discord_raw.get("username"), "MÁP+ értesítő"),
        avatar_url=_as_str(discord_raw.get("avatar_url"), ""),
    )

    windows = WindowsSettings(
        enabled=_as_bool(windows_raw.get("enabled"), False),
    )

    webhook_headers_raw = webhook_raw.get("headers", {})
    if webhook_headers_raw is None:
        webhook_headers_raw = {}
    if not isinstance(webhook_headers_raw, dict):
        raise ConfigError("[notifiers.webhook.headers] nem táblázat.")
    webhook = WebhookSettings(
        enabled=_as_bool(webhook_raw.get("enabled"), False),
        url=_as_str(webhook_raw.get("url"), ""),
        headers={str(k): str(v) for k, v in webhook_headers_raw.items()},
    )

    reminder = ReminderSettings(
        enabled=_as_bool(reminder_raw.get("enabled"), False),
        delay_hours=_as_int(reminder_raw.get("delay_hours"), 24, "reminder.delay_hours"),
        text=_as_str(
            reminder_raw.get("text"),
            "Ne feledd: az új MÁP+ sorozat megvásárlásához a vételárat is "
            "rendezned kell.",
        ),
    )

    config = Config(
        path=config_path,
        app=app,
        console=console,
        ntfy=ntfy,
        email=email,
        telegram=telegram,
        discord=discord,
        windows=windows,
        webhook=webhook,
        reminder=reminder,
    )
    _validate(config)
    return config


def _validate(config: Config) -> None:
    app = config.app
    if not 30 <= app.lookback_days <= 3650:
        raise ConfigError("app.lookback_days értéke 30 és 3650 között legyen.")
    if not 1 <= app.announce_horizon_days <= 365:
        raise ConfigError("app.announce_horizon_days értéke 1 és 365 között legyen.")
    if not 0 <= app.ending_soon_days <= 90:
        raise ConfigError("app.ending_soon_days értéke 0 és 90 között legyen.")
    if not 5 <= app.http_timeout_seconds <= 120:
        raise ConfigError("app.http_timeout_seconds értéke 5 és 120 között legyen.")

    if not config.enabled_notifier_names:
        raise ConfigError(
            "Nincs bekapcsolt értesítési csatorna. Kapcsold be legalább a "
            "[notifiers.console] szakaszt, vagy állíts be e-mailt/Telegramot/ntfy-t."
        )

    if config.email.enabled:
        email = config.email
        if not email.host:
            raise ConfigError("Az e-mail értesítéshez add meg a host értékét.")
        if not email.to:
            raise ConfigError("Az e-mail értesítéshez add meg legalább egy címzettet.")
        if not (email.from_addr or email.username):
            raise ConfigError("Az e-mail értesítéshez add meg a feladót (from) vagy a username-et.")
        if not 1 <= email.port <= 65535:
            raise ConfigError("notifiers.email.port értéke 1 és 65535 között legyen.")
        if email.ssl and email.starttls:
            raise ConfigError("Az e-mailnél az ssl és a starttls nem lehet egyszerre igaz.")
        if email.username and not email.password:
            raise ConfigError(
                "Az e-mail felhasználónévhez jelszó is kell. Használhatsz környezeti "
                "változót, például: password = \"${SMTP_PASSWORD}\"."
            )

    if config.telegram.enabled:
        if not config.telegram.bot_token:
            raise ConfigError(
                "A Telegram értesítéshez add meg a bot_token értékét "
                "(pl. bot_token = \"${TELEGRAM_BOT_TOKEN}\")."
            )
        if not config.telegram.chat_id:
            raise ConfigError("A Telegram értesítéshez add meg a chat_id értékét.")
        if config.telegram.message_thread_id < 0:
            raise ConfigError("notifiers.telegram.message_thread_id nem lehet negatív.")

    if config.discord.enabled:
        if not config.discord.webhook_url:
            raise ConfigError(
                "A Discord értesítéshez add meg a webhook_url értékét "
                "(pl. webhook_url = \"${DISCORD_WEBHOOK_URL}\")."
            )
        if not config.discord.webhook_url.startswith("https://"):
            raise ConfigError("A Discord webhook_url https:// címmel kezdődjön.")
        if "/api/webhooks/" not in config.discord.webhook_url:
            raise ConfigError(
                "A Discord webhook_url nem tűnik webhook URL-nek "
                "(hiányzik belőle az /api/webhooks/ rész)."
            )

    if config.ntfy.enabled:
        if not config.ntfy.topic:
            raise ConfigError(
                "Az ntfy értesítéshez válassz egy témát, például: "
                "topic = \"map-plusz-7f3k9q2x\"."
            )
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", config.ntfy.topic):
            raise ConfigError(
                "Az ntfy topic 1–64 karakter lehet, csak betű, szám, "
                "aláhúzás és kötőjel."
            )
        if not config.ntfy.url.startswith(("http://", "https://")):
            raise ConfigError("Az ntfy url értéke http:// vagy https:// legyen.")
        if config.ntfy.priority not in _VALID_NTFY_PRIORITIES:
            raise ConfigError(
                "Az ntfy priority értéke: min, low, default, high vagy urgent."
            )

    if config.webhook.enabled and not config.webhook.url.startswith(("http://", "https://")):
        raise ConfigError("A webhook url értéke http:// vagy https:// legyen.")

    if config.windows.enabled and sys.platform != "win32":
        raise ConfigError("A Windows értesítés csak Windows rendszeren használható.")

    if not 0 <= config.reminder.delay_hours <= 168:
        raise ConfigError("reminder.delay_hours értéke 0 és 168 között legyen.")
    if config.reminder.enabled and not config.reminder.text:
        raise ConfigError("A reminder.text nem lehet üres, ha az emlékeztető be van kapcsolva.")
