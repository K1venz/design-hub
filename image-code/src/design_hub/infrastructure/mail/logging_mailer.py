"""Explicit development mail sink that never logs message content."""

import structlog

from design_hub.ports.mail import MailPort

log = structlog.get_logger(__name__)


class LoggingMailer(MailPort):
    async def send(self, *, to: str, subject: str, body_text: str) -> None:
        log.info(
            "mail.delivery_skipped",
            to=to,
            subject=subject,
            body_bytes=len(body_text.encode()),
        )
