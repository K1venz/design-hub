"""SMTP mailer (stdlib smtplib, off event loop via to_thread)."""

import asyncio
import smtplib
from email.message import EmailMessage

from design_hub.ports.mail import MailPort


class SmtpMailer(MailPort):
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        from_addr: str,
        use_tls: bool = True,
    ) -> None:
        if not host or not from_addr:
            raise ValueError("SMTP host and from address are required")
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from = from_addr
        self._use_tls = use_tls

    async def send(self, *, to: str, subject: str, body_text: str) -> None:
        msg = EmailMessage()
        msg["From"] = self._from
        msg["To"] = to
        msg["Subject"] = subject
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
            smtp.send_message(msg, from_addr=self._from, to_addrs=[to])
