"""Dev/fallback mailer: structured log only (no network)."""

import structlog

from design_hub.ports.mail import MailPort

log = structlog.get_logger(__name__)


class LoggingMailer(MailPort):
    async def send(self, *, to: str, subject: str, body_text: str) -> None:
        log.info(
            "mail.sent_via_log",
            to=to,
            subject=subject,
            body=body_text,
        )
