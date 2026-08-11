"""Registration challenge persistence boundary."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from design_hub.ports.user_repository import UserAccount


class RegistrationDeliveryState(StrEnum):
    PENDING = "pending_delivery"
    ACTIVE = "active"
    CONSUMED = "consumed"


@dataclass(frozen=True)
class RegistrationChallenge:
    id: str
    delivery_id: str
    email: str
    name: str
    password_hash: str
    code_hash: str
    delivery_state: RegistrationDeliveryState
    expires_at: datetime
    attempt_count: int
    created_at: datetime
    delivery_claimed_at: datetime
    activated_at: datetime | None
    consumed_at: datetime | None


@dataclass(frozen=True)
class RegistrationClaimed:
    challenge: RegistrationChallenge


@dataclass(frozen=True)
class RegistrationCooldown:
    retry_after_seconds: int


@dataclass(frozen=True)
class RegistrationClaimContended:
    retry_after_seconds: int = 1


@dataclass(frozen=True)
class RegistrationAlreadyRegistered:
    pass


@dataclass(frozen=True)
class RegistrationClaimInvalid:
    pass


type InitialRegistrationClaim = (
    RegistrationClaimed
    | RegistrationCooldown
    | RegistrationClaimContended
    | RegistrationAlreadyRegistered
)
type ResendRegistrationClaim = (
    RegistrationClaimed
    | RegistrationCooldown
    | RegistrationClaimContended
    | RegistrationClaimInvalid
)


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
    async def claim_initial(
        self,
        *,
        email: str,
        name: str,
        password_hash: str,
        code_hash: str,
        expires_at: datetime,
        claimed_at: datetime,
        cooldown_seconds: int,
    ) -> InitialRegistrationClaim:
        """Atomically claim the right to deliver a new registration challenge."""

    @abstractmethod
    async def claim_resend(
        self,
        *,
        email: str,
        challenge_id: str,
        code_hash: str,
        expires_at: datetime,
        claimed_at: datetime,
        cooldown_seconds: int,
    ) -> ResendRegistrationClaim:
        """Atomically claim resend for the expected browser challenge."""

    @abstractmethod
    async def activate(
        self,
        *,
        challenge_id: str,
        delivery_id: str,
        activated_at: datetime,
    ) -> RegistrationChallenge | None:
        """Make exactly the expected delivered code verifiable."""

    @abstractmethod
    async def get_active(
        self,
        *,
        email: str,
        challenge_id: str,
    ) -> RegistrationChallenge | None:
        """Return only an active challenge bound to the browser identity."""

    @abstractmethod
    async def record_failed_attempt(
        self,
        *,
        challenge_id: str,
        delivery_id: str,
    ) -> RegistrationChallenge | None:
        """Increment only the expected active delivery."""

    @abstractmethod
    async def invalidate(
        self,
        *,
        challenge_id: str,
        delivery_id: str,
        invalidated_at: datetime,
    ) -> bool:
        """Consume the expected delivery without creating an account."""

    @abstractmethod
    async def complete(
        self,
        *,
        expected: RegistrationChallenge,
        completed_at: datetime,
    ) -> RegistrationCompletion:
        """Atomically create the account and consume an unchanged active challenge."""
