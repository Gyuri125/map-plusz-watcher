"""Értesítési csatornák közös interfésze."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from ..models import Message

logger = logging.getLogger("allampapir.notify")


class NotifierError(RuntimeError):
    """Egy értesítési csatorna küldése sikertelen."""


class Notifier(ABC):
    name: str

    @property
    def is_console(self) -> bool:
        return False

    @abstractmethod
    def send(self, message: Message) -> None:
        """Elküldi az értesítést. Hiba esetén NotifierError-t dob."""


@dataclass
class DispatchResult:
    successes: list[str] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)
    delivered: bool = False

    @property
    def ok(self) -> bool:
        return self.delivered and not self.failures


class NotifierManager:
    def __init__(
        self,
        notifiers: list[Notifier],
        attachment_provider: Callable[[], Path | None] | None = None,
    ) -> None:
        self.notifiers = notifiers
        self.attachment_provider = attachment_provider
        self._attachment: Path | None = None
        self._attachment_ready = False

    @property
    def names(self) -> list[str]:
        return [notifier.name for notifier in self.notifiers]

    def begin_cycle(self) -> None:
        """Új ellenőrzési ciklus: a csatolmányt újra kell kérni."""
        self._attachment = None
        self._attachment_ready = False

    def _get_attachment(self) -> Path | None:
        if self._attachment_ready:
            return self._attachment
        self._attachment_ready = True
        if self.attachment_provider is None:
            return None
        try:
            attachment = self.attachment_provider()
        except Exception as exc:
            logger.warning("A grafikon előállítása sikertelen: %s", exc)
            return None
        if attachment is not None and not Path(attachment).is_file():
            logger.warning("A grafikonfájl nem található: %s", attachment)
            return None
        self._attachment = Path(attachment) if attachment is not None else None
        return self._attachment

    def send(self, message: Message) -> DispatchResult:
        result = DispatchResult()
        real_notifiers = [item for item in self.notifiers if not item.is_console]

        attachment = self._get_attachment()
        if attachment is not None:
            message = replace(message, image_path=attachment)

        for notifier in self.notifiers:
            try:
                notifier.send(message)
                result.successes.append(notifier.name)
            except Exception as exc:
                text = str(exc).strip() or type(exc).__name__
                result.failures.append((notifier.name, text))
                logger.error(
                    "Nem sikerült elküldeni a(z) %s értesítést: %s",
                    notifier.name,
                    text,
                )
                logger.debug("Részletek:", exc_info=True)

        if real_notifiers:
            result.delivered = any(
                notifier.name in result.successes for notifier in real_notifiers
            )
        else:
            result.delivered = "console" in result.successes

        if result.successes:
            logger.info("Értesítés elküldve: %s", ", ".join(result.successes))
        if result.failures:
            logger.warning(
                "Sikertelen csatornák: %s",
                ", ".join(name for name, _ in result.failures),
            )
        return result
