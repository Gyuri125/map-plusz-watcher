"""Windows 10/11 rendszerértesítés a winotify csomaggal."""

from __future__ import annotations

import sys

from ..config import WindowsSettings
from ..messages import WEBKINCSTAR_URL
from ..models import Message
from ..util import truncate
from .base import Notifier, NotifierError


class WindowsNotifier(Notifier):
    name = "windows"

    def __init__(self, settings: WindowsSettings) -> None:
        self.settings = settings

    def send(self, message: Message) -> None:
        if sys.platform != "win32":
            raise NotifierError("A Windows értesítés csak Windows rendszeren működik.")
        try:
            from winotify import Notification, audio
        except ImportError as exc:
            raise NotifierError(
                "A Windows értesítéshez telepítsd a winotify csomagot: "
                "pip install winotify"
            ) from exc

        body = truncate(message.body, 240)
        try:
            toast = Notification(
                app_id="MÁP+ értesítő",
                title=message.title,
                msg=body,
                duration="long",
            )
            if message.series is not None:
                toast.add_actions(label="WebKincstár", launch=WEBKINCSTAR_URL)
            toast.set_audio(audio.Default, loop=False)
            toast.show()
        except Exception as exc:
            raise NotifierError(f"Windows értesítési hiba: {exc}") from exc
