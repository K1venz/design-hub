"""Outbound mail port (password reset and future transactional email)."""

from abc import ABC, abstractmethod


class MailPort(ABC):
    @abstractmethod
    async def send(self, *, to: str, subject: str, body_text: str) -> None:
        """Deliver a plain-text email. Network/IO failures raise; caller decides retry."""
