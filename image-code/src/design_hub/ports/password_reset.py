"""Password-reset challenge store (one active challenge per email)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PasswordResetChallenge:
    id: str
    email: str
    code_hash: str
    expires_at: datetime
    attempt_count: int
    created_at: datetime
    consumed_at: datetime | None


class PasswordResetStore(ABC):
    @abstractmethod
    async def get_active(self, email: str) -> PasswordResetChallenge | None:
        """Latest unconsumed challenge for email, or None."""

    @abstractmethod
    async def replace_active(
        self,
        *,
        email: str,
        code_hash: str,
        expires_at: datetime,
    ) -> PasswordResetChallenge:
        """Invalidate prior unconsumed challenges and create a new one."""

    @abstractmethod
    async def record_failed_attempt(self, challenge_id: str) -> PasswordResetChallenge | None:
        """Increment attempt_count; return updated row or None if missing/consumed."""

    @abstractmethod
    async def consume(self, challenge_id: str) -> None:
        """Mark challenge used (idempotent if already consumed)."""
