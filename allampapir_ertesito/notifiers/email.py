"""E-mail értesítés SMTP-n keresztül."""

from __future__ import annotations

import html
import smtplib
import ssl
from email.message import EmailMessage

from ..config import EmailSettings
from ..models import Message
from .base import Notifier, NotifierError


class EmailNotifier(Notifier):
    name = "email"

    def __init__(self, settings: EmailSettings) -> None:
        self.settings = settings

    def send(self, message: Message) -> None:
        settings = self.settings
        sender = settings.from_addr or settings.username
        if not sender:
            raise NotifierError("Nincs beállítva e-mail feladó.")
        if not settings.to:
            raise NotifierError("Nincs beállítva e-mail címzett.")

        email = EmailMessage()
        email["Subject"] = message.title
        email["From"] = sender
        email["To"] = ", ".join(settings.to)
        email.set_content(message.body)
        html_body = (
            "<html><body>"
            "<pre style=\"white-space: pre-wrap; font-family: 'Segoe UI', Arial, sans-serif; "
            "font-size: 14px; line-height: 1.5;\">"
            f"{html.escape(message.body)}"
            "</pre></body></html>"
        )
        email.add_alternative(html_body, subtype="html")

        try:
            if settings.ssl:
                server: smtplib.SMTP = smtplib.SMTP_SSL(
                    settings.host,
                    settings.port,
                    timeout=settings.timeout,
                    context=ssl.create_default_context(),
                )
            else:
                server = smtplib.SMTP(
                    settings.host,
                    settings.port,
                    timeout=settings.timeout,
                )

            with server:
                server.ehlo()
                if settings.starttls and not settings.ssl:
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                if settings.username:
                    server.login(settings.username, settings.password)
                server.send_message(email)
        except smtplib.SMTPAuthenticationError as exc:
            raise NotifierError(
                "Az SMTP szerver elutasította a bejelentkezést. Gmailnél "
                "alkalmazásjelszót kell használni."
            ) from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise NotifierError(f"SMTP hiba: {exc}") from exc
