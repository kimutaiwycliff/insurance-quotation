"""SMTP sender (stdlib smtplib in a worker thread: email is sent from background jobs, not requests)."""

import asyncio
import smtplib
from email.headerregistry import Address
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import make_msgid

from app.core.config import Settings
from app.integrations.email import EmailSendError, OutboundEmail

_POLICY = SMTP.clone(max_line_length=998)


class SmtpSender:
    def __init__(self, settings: Settings) -> None:
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._username = settings.smtp_username
        self._password = (
            settings.smtp_password.get_secret_value() if settings.smtp_password else None
        )
        self._starttls = settings.smtp_starttls
        self._domain = settings.email_from_address.rpartition("@")[2] or "localhost"

    def _build(self, message: OutboundEmail) -> EmailMessage:
        # RFC 5322 allows 998-char lines: long header values (List-Unsubscribe URLs) stay unfolded and
        # are never turned into encoded-words, which some clients cannot parse.
        mail = EmailMessage(policy=_POLICY)
        local, _, domain = message.from_address.partition("@")
        mail["From"] = Address(display_name=message.from_name, username=local, domain=domain)
        mail["To"] = message.to
        mail["Subject"] = message.subject
        if message.reply_to:
            mail["Reply-To"] = message.reply_to
        mail["Message-ID"] = make_msgid(domain=self._domain)
        for name, value in message.headers.items():
            mail[name] = value
        mail.set_content(message.text)
        if message.html:
            mail.add_alternative(message.html, subtype="html")
        return mail

    def _send_sync(self, mail: EmailMessage) -> None:
        with smtplib.SMTP(self._host, self._port, timeout=15) as smtp:
            if self._starttls:
                smtp.starttls()
            if self._username and self._password:
                smtp.login(self._username, self._password)
            smtp.send_message(mail)

    async def send(self, message: OutboundEmail) -> str:
        mail = self._build(message)
        try:
            await asyncio.to_thread(self._send_sync, mail)
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailSendError(f"SMTP send failed ({type(exc).__name__})") from exc
        return str(mail["Message-ID"])
