"""Képernyős/naplóértesítés."""

from __future__ import annotations

import logging

from ..models import Message
from .base import Notifier, NotifierError

logger = logging.getLogger("allampapir.notify.console")


class ConsoleNotifier(Notifier):
    name = "console"

    @property
    def is_console(self) -> bool:
        return True

    def send(self, message: Message) -> None:
        separator = "=" * 72
        try:
            # A loggeren keresztül a naplófájlba is bekerül a teljes üzenet,
            # ami Feladatütemezőből indítva különösen hasznos.
            logger.info(
                "\n%s\n%s\n%s\n%s\n",
                separator,
                message.title,
                separator,
                message.body,
            )
        except (OSError, UnicodeError) as exc:
            raise NotifierError(f"Nem sikerült a naplóba írni: {exc}") from exc
