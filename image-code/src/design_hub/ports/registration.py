"""Pending-registration persistence boundary."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from design_hub.ports.user_repository import UserAccount


@dataclass(frozen=True)
class PendingRegistration:
    id: str
    email: str
    name: str
    password_hash: str
    code_hash: str
    expires_at: datetime
    attempt_count: int
    created_at: datetime
    last_sent_at: datetime
    consumed_at: datetime | None


@dataclass(frozen=True)
class RegistrationCompleted:
    account: UserAccount


@dataclass(frozen=True)
class RegistrationDuplicate:
    pass


@dataclass(frozen=True)
class RegistrationInvalid:
    pass


type RegistrationCompletion = RegistrationCompleted | RegistrationDuplicate | RegistrationInvalid


class RegistrationStore(ABC):
    @abstractmethod
    async def get_active(self, email: str) -> PendingRegistration | None:
        """Return the current unconsumed challenge for a normalized email."""

    @abstractmethod
    async def replace_active(
        self,
        *,
        email: str,
        name: str,
        password_hash: str,
        code_hash: str,
        expires_at: datetime,
        sent_at: datetime,
    ) -> PendingRegistration:
        """Replace the current challenge while reusing the email's single row."""

    @abstractmethod
    async def record_failed_attempt(self, challenge_id: str) -> PendingRegistration | None:
        """Increment only the current unconsumed challenge."""

    @abstractmethod
    async def invalidate(self, *, challenge_id: str, invalidated_at: datetime) -> None:
        """Consume the current challenge without creating an account."""

    @abstractmethod
    async def complete(
        self,
        *,
        expected: PendingRegistration,
        completed_at: datetime,
    ) -> RegistrationCompletion:
        """Atomically create the account and consume an unchanged valid challenge."""
