"""Értesítési csatornák közös interfésze."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

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
    def __init__(self, notifiers: list[Notifier]) -> None:
        self.notifiers = notifiers

    @property
    def names(self) -> list[str]:
        return [notifier.name for notifier in self.notifiers]

    def send(self, message: Message) -> DispatchResult:
        result = DispatchResult()
        real_notifiers = [item for item in self.notifiers if not item.is_console]

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
