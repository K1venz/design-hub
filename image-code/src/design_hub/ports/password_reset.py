"""Password-reset delivery and completion persistence boundary."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class PasswordResetDeliveryState(StrEnum):
    PENDING = "pending_delivery"
    ACTIVE = "active"
    CONSUMED = "consumed"


@dataclass(frozen=True)
class PasswordResetChallenge:
    id: str
    delivery_id: str
    email: str
    code_hash: str
    delivery_state: PasswordResetDeliveryState
    expires_at: datetime
    attempt_count: int
    created_at: datetime
    delivery_claimed_at: datetime
    activated_at: datetime | None
    consumed_at: datetime | None


@dataclass(frozen=True)
class PasswordResetClaimed:
    challenge: PasswordResetChallenge


@dataclass(frozen=True)
class PasswordResetCooldown:
    retry_after_seconds: int


@dataclass(frozen=True)
class PasswordResetClaimContended:
    retry_after_seconds: int = 1


@dataclass(frozen=True)
class PasswordResetAccountUnavailable:
    pass


type PasswordResetClaim = (
    PasswordResetClaimed
    | PasswordResetCooldown
    | PasswordResetClaimContended
    | PasswordResetAccountUnavailable
)


@dataclass(frozen=True)
class PasswordResetCompleted:
    pass


@dataclass(frozen=True)
class PasswordResetInvalid:
    pass


@dataclass(frozen=True)
class PasswordResetAttemptsExceeded:
    pass


type PasswordResetCompletion = (
    PasswordResetCompleted | PasswordResetInvalid | PasswordResetAttemptsExceeded
)


class PasswordResetStore(ABC):
    @abstractmethod
    async def claim(
        self,
        *,
        email: str,
        code_hash: str,
        expires_at: datetime,
        claimed_at: datetime,
        cooldown_seconds: int,
    ) -> PasswordResetClaim:
        """Atomically claim the right to deliver a reset code to an enabled account."""

    @abstractmethod
    async def activate(
        self,
        *,
        challenge_id: str,
        delivery_id: str,
        activated_at: datetime,
    ) -> PasswordResetChallenge | None:
        """Make exactly the expected delivered code verifiable."""

    @abstractmethod
    async def get_active(self, *, email: str) -> PasswordResetChallenge | None:
        """Return only the active reset challenge for an email."""

    @abstractmethod
    async def invalidate(
        self,
        *,
        challenge_id: str,
        delivery_id: str,
        invalidated_at: datetime,
    ) -> bool:
        """Consume the expected delivery after delivery or activation failure."""

    @abstractmethod
    async def complete(
        self,
        *,
        email: str,
        code_hash: str,
        password_hash_factory: Callable[[], str],
        completed_at: datetime,
        max_attempts: int,
    ) -> PasswordResetCompletion:
        """Atomically consume a valid code and update the enabled account password."""
