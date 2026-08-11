"""SMTP mailer (stdlib smtplib, off event loop via to_thread)."""

import asyncio
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime, formataddr, make_msgid

from design_hub.ports.mail import MailPort


class SmtpMailer(MailPort):
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        from_name: str,
        from_addr: str,
        use_tls: bool = True,
    ) -> None:
        if not host or not from_name or not from_addr:
            raise ValueError("SMTP host, from name, and from address are required")
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_name = from_name
        self._from_addr = from_addr
        self._from_domain = from_addr.rsplit("@", 1)[1]
        self._use_tls = use_tls

    async def send(self, *, to: str, subject: str, body_text: str) -> None:
        msg = EmailMessage()
        msg["From"] = formataddr((self._from_name, self._from_addr))
        msg["To"] = to
        msg["Subject"] = subject
        msg["Date"] = format_datetime(datetime.now(UTC))
        msg["Message-ID"] = make_msgid(domain=self._from_domain)
        msg["Auto-Submitted"] = "auto-generated"
        msg.set_content(body_text)
        await asyncio.to_thread(self._deliver, msg, to)

    def _deliver(self, msg: EmailMessage, to: str) -> None:
        with smtplib.SMTP(self._host, self._port, timeout=30) as smtp:
            smtp.ehlo()
            if self._use_tls:
                smtp.starttls()
                smtp.ehlo()
            if self._username:
                smtp.login(self._username, self._password)
            smtp.send_message(msg, from_addr=self._from_addr, to_addrs=[to])
