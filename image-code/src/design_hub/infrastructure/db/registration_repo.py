"""SQLAlchemy store for registration delivery claims and verification."""

import math
import re
import secrets
import sqlite3
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.enums import Role
from design_hub.infrastructure.db.models import AppUser, RegistrationChallengeRow
from design_hub.ports.registration import (
    InitialRegistrationClaim,
    RegistrationAlreadyRegistered,
    RegistrationChallenge,
    RegistrationClaimContended,
    RegistrationClaimed,
    RegistrationClaimInvalid,
    RegistrationCompleted,
    RegistrationCompletion,
    RegistrationCooldown,
    RegistrationDeliveryState,
    RegistrationDuplicate,
    RegistrationInvalid,
    RegistrationStore,
    ResendRegistrationClaim,
)
from design_hub.ports.user_repository import UserAccount

_APP_USER_EMAIL_CONSTRAINT = "uq_app_user_email"
_REGISTRATION_EMAIL_CONSTRAINT = "uq_registration_challenge_email"
_POSTGRES_UNIQUE_CONSTRAINT = re.compile(
    r'duplicate key value violates unique constraint "(?P<constraint>[^"]+)"(?:\n|$)',
    re.IGNORECASE,
)
_MYSQL_DUPLICATE_KEY = re.compile(
    r"for key [`'](?P<constraint>[^`']+)[`']$",
    re.IGNORECASE,
)
_SQLITE_CLAIM_CONTENTION = {
    "database is locked",
    "database table is locked",
    "database schema is locked",
}
_POSTGRES_CLAIM_CONTENTION = {"40001", "40P01"}
_MYSQL_CLAIM_CONTENTION = {1205, 1213}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_challenge(row: RegistrationChallengeRow) -> RegistrationChallenge:
    return RegistrationChallenge(
        id=row.id,
        delivery_id=row.delivery_id,
        email=row.email,
        name=row.name,
        password_hash=row.password_hash,
        code_hash=row.code_hash,
        delivery_state=RegistrationDeliveryState(row.delivery_state),
        expires_at=_utc(row.expires_at),
        attempt_count=row.attempt_count,
        created_at=_utc(row.created_at),
        delivery_claimed_at=_utc(row.delivery_claimed_at),
        activated_at=_utc(row.activated_at) if row.activated_at is not None else None,
        consumed_at=_utc(row.consumed_at) if row.consumed_at is not None else None,
    )


def _to_account(row: AppUser) -> UserAccount:
    return UserAccount(
        id=row.id,
        email=row.email,
        name=row.name,
        role=Role(row.role),
        created_at=_utc(row.created_at),
        password_hash=row.password_hash,
        enabled=row.enabled,
        disabled_at=_utc(row.disabled_at) if row.disabled_at is not None else None,
        disabled_by=row.disabled_by,
        disabled_reason=row.disabled_reason,
    )


def _unique_constraint(error: IntegrityError) -> str | None:
    original: Any = error.orig
    args = getattr(original, "args", ())
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    if sqlstate == "23505":
        diagnostic = getattr(original, "diag", None)
        constraint = getattr(original, "constraint_name", None) or getattr(
            diagnostic,
            "constraint_name",
            None,
        )
        if constraint is not None:
            return str(constraint)
        match = _POSTGRES_UNIQUE_CONSTRAINT.search(str(original))
        return match.group("constraint") if match is not None else None

    if isinstance(original, sqlite3.IntegrityError):
        message = str(original).strip().casefold()
        sqlite_constraints = {
            "unique constraint failed: app_user.email": _APP_USER_EMAIL_CONSTRAINT,
            "unique constraint failed: registration_challenge.email": (
                _REGISTRATION_EMAIL_CONSTRAINT
            ),
        }
        return sqlite_constraints.get(message)

    if not args or args[0] != 1062 or len(args) < 2 or not isinstance(args[1], str):
        return None
    match = _MYSQL_DUPLICATE_KEY.search(args[1])
    if match is None:
        return None
    return match.group("constraint").rsplit(".", maxsplit=1)[-1]


def _is_app_user_email_duplicate(error: IntegrityError) -> bool:
    return _unique_constraint(error) == _APP_USER_EMAIL_CONSTRAINT


def _is_registration_email_duplicate(error: IntegrityError) -> bool:
    return _unique_constraint(error) == _REGISTRATION_EMAIL_CONSTRAINT


def _is_registration_claim_contention(error: DBAPIError) -> bool:
    if isinstance(error, IntegrityError) and _is_registration_email_duplicate(error):
        return True
    original: Any = error.orig
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    if sqlstate in _POSTGRES_CLAIM_CONTENTION:
        return True
    args = getattr(original, "args", ())
    if args and args[0] in _MYSQL_CLAIM_CONTENTION:
        return True
    return isinstance(original, sqlite3.OperationalError) and str(original).casefold() in (
        _SQLITE_CLAIM_CONTENTION
    )


def _new_id() -> str:
    return secrets.token_urlsafe(32)


def _cooldown_remaining(
    *,
    previous_claimed_at: datetime,
    claimed_at: datetime,
    cooldown_seconds: int,
) -> int:
    age = (_utc(claimed_at) - _utc(previous_claimed_at)).total_seconds()
    return max(0, math.ceil(cooldown_seconds - age))


class SqlAlchemyRegistrationStore(RegistrationStore):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

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
        claimed_at_utc = _utc(claimed_at)
        expires_at_utc = _utc(expires_at)
        challenge_id = _new_id()
        delivery_id = _new_id()
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    user_id = await session.scalar(select(AppUser.id).where(AppUser.email == email))
                    if user_id is not None:
                        return RegistrationAlreadyRegistered()

                    row = (
                        await session.execute(
                            select(RegistrationChallengeRow)
                            .where(RegistrationChallengeRow.email == email)
                            .with_for_update()
                        )
                    ).scalar_one_or_none()
                    if row is not None:
                        remaining = _cooldown_remaining(
                            previous_claimed_at=row.delivery_claimed_at,
                            claimed_at=claimed_at_utc,
                            cooldown_seconds=cooldown_seconds,
                        )
                        if remaining > 0:
                            return RegistrationCooldown(remaining)
                        row.id = challenge_id
                        row.delivery_id = delivery_id
                        row.name = name
                        row.password_hash = password_hash
                        row.code_hash = code_hash
                        row.delivery_state = RegistrationDeliveryState.PENDING.value
                        row.expires_at = expires_at_utc
                        row.attempt_count = 0
                        row.created_at = claimed_at_utc
                        row.delivery_claimed_at = claimed_at_utc
                        row.activated_at = None
                        row.consumed_at = None
                    else:
                        row = RegistrationChallengeRow(
                            id=challenge_id,
                            delivery_id=delivery_id,
                            email=email,
                            name=name,
                            password_hash=password_hash,
                            code_hash=code_hash,
                            delivery_state=RegistrationDeliveryState.PENDING.value,
                            expires_at=expires_at_utc,
                            attempt_count=0,
                            created_at=claimed_at_utc,
                            delivery_claimed_at=claimed_at_utc,
                            activated_at=None,
                            consumed_at=None,
                        )
                        session.add(row)
                    await session.flush()
                    return RegistrationClaimed(_to_challenge(row))
        except DBAPIError as error:
            if _is_registration_claim_contention(error):
                return RegistrationClaimContended()
            raise

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
        claimed_at_utc = _utc(claimed_at)
        expires_at_utc = _utc(expires_at)
        replacement_challenge_id = _new_id()
        delivery_id = _new_id()
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    row = (
                        await session.execute(
                            select(RegistrationChallengeRow)
                            .where(
                                RegistrationChallengeRow.email == email,
                                RegistrationChallengeRow.id == challenge_id,
                                RegistrationChallengeRow.consumed_at.is_(None),
                                RegistrationChallengeRow.delivery_state.in_(
                                    (
                                        RegistrationDeliveryState.PENDING.value,
                                        RegistrationDeliveryState.ACTIVE.value,
                                    )
                                ),
                            )
                            .with_for_update()
                        )
                    ).scalar_one_or_none()
                    if row is None:
                        return RegistrationClaimInvalid()
                    remaining = _cooldown_remaining(
                        previous_claimed_at=row.delivery_claimed_at,
                        claimed_at=claimed_at_utc,
                        cooldown_seconds=cooldown_seconds,
                    )
                    if remaining > 0:
                        return RegistrationCooldown(remaining)

                    row.id = replacement_challenge_id
                    row.delivery_id = delivery_id
                    row.code_hash = code_hash
                    row.delivery_state = RegistrationDeliveryState.PENDING.value
                    row.expires_at = expires_at_utc
                    row.attempt_count = 0
                    row.delivery_claimed_at = claimed_at_utc
                    row.activated_at = None
                    await session.flush()
                    return RegistrationClaimed(_to_challenge(row))
        except DBAPIError as error:
            if _is_registration_claim_contention(error):
                return RegistrationClaimContended()
            raise

    async def activate(
        self,
        *,
        challenge_id: str,
        delivery_id: str,
        activated_at: datetime,
    ) -> RegistrationChallenge | None:
        activated_at_utc = _utc(activated_at)
        async with self._session_factory() as session:
            async with session.begin():
                result = cast(
                    CursorResult[Any],
                    await session.execute(
                        update(RegistrationChallengeRow)
                        .where(
                            RegistrationChallengeRow.id == challenge_id,
                            RegistrationChallengeRow.delivery_id == delivery_id,
                            RegistrationChallengeRow.delivery_state
                            == RegistrationDeliveryState.PENDING.value,
                            RegistrationChallengeRow.expires_at > activated_at_utc,
                            RegistrationChallengeRow.consumed_at.is_(None),
                        )
                        .values(
                            delivery_state=RegistrationDeliveryState.ACTIVE.value,
                            activated_at=activated_at_utc,
                        )
                    ),
                )
                if result.rowcount != 1:
                    return None
                row = await session.get(RegistrationChallengeRow, challenge_id)
                if row is None:
                    raise RuntimeError("activated registration challenge disappeared")
                return _to_challenge(row)

    async def get_active(
        self,
        *,
        email: str,
        challenge_id: str,
    ) -> RegistrationChallenge | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(RegistrationChallengeRow).where(
                        RegistrationChallengeRow.email == email,
                        RegistrationChallengeRow.id == challenge_id,
                        RegistrationChallengeRow.delivery_state
                        == RegistrationDeliveryState.ACTIVE.value,
                        RegistrationChallengeRow.consumed_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            return _to_challenge(row) if row is not None else None

    async def record_failed_attempt(
        self,
        *,
        challenge_id: str,
        delivery_id: str,
    ) -> RegistrationChallenge | None:
        async with self._session_factory() as session:
            async with session.begin():
                result = cast(
                    CursorResult[Any],
                    await session.execute(
                        update(RegistrationChallengeRow)
                        .where(
                            RegistrationChallengeRow.id == challenge_id,
                            RegistrationChallengeRow.delivery_id == delivery_id,
                            RegistrationChallengeRow.delivery_state
                            == RegistrationDeliveryState.ACTIVE.value,
                            RegistrationChallengeRow.consumed_at.is_(None),
                        )
                        .values(attempt_count=RegistrationChallengeRow.attempt_count + 1)
                    ),
                )
                if result.rowcount != 1:
                    return None
                row = await session.get(RegistrationChallengeRow, challenge_id)
                if row is None:
                    raise RuntimeError("updated registration challenge disappeared")
                return _to_challenge(row)

    async def invalidate(
        self,
        *,
        challenge_id: str,
        delivery_id: str,
        invalidated_at: datetime,
    ) -> bool:
        invalidated_at_utc = _utc(invalidated_at)
        async with self._session_factory() as session:
            async with session.begin():
                result = cast(
                    CursorResult[Any],
                    await session.execute(
                        update(RegistrationChallengeRow)
                        .where(
                            RegistrationChallengeRow.id == challenge_id,
                            RegistrationChallengeRow.delivery_id == delivery_id,
                            RegistrationChallengeRow.consumed_at.is_(None),
                        )
                        .values(
                            delivery_state=RegistrationDeliveryState.CONSUMED.value,
                            consumed_at=invalidated_at_utc,
                        )
                    ),
                )
                return result.rowcount == 1

    async def complete(
        self,
        *,
        expected: RegistrationChallenge,
        completed_at: datetime,
    ) -> RegistrationCompletion:
        expected_expires_at = _utc(expected.expires_at)
        completed_at_utc = _utc(completed_at)
        if (
            expected.delivery_state is not RegistrationDeliveryState.ACTIVE
            or expected.activated_at is None
            or expected.consumed_at is not None
            or expected_expires_at <= completed_at_utc
        ):
            return RegistrationInvalid()

        try:
            async with self._session_factory() as session:
                async with session.begin():
                    consumed = cast(
                        CursorResult[Any],
                        await session.execute(
                            update(RegistrationChallengeRow)
                            .where(
                                RegistrationChallengeRow.id == expected.id,
                                RegistrationChallengeRow.delivery_id == expected.delivery_id,
                                RegistrationChallengeRow.email == expected.email,
                                RegistrationChallengeRow.code_hash == expected.code_hash,
                                RegistrationChallengeRow.delivery_state
                                == RegistrationDeliveryState.ACTIVE.value,
                                RegistrationChallengeRow.expires_at == expected_expires_at,
                                RegistrationChallengeRow.expires_at > completed_at_utc,
                                RegistrationChallengeRow.attempt_count == expected.attempt_count,
                                RegistrationChallengeRow.consumed_at.is_(None),
                            )
                            .values(
                                delivery_state=RegistrationDeliveryState.CONSUMED.value,
                                consumed_at=completed_at_utc,
                            )
                        ),
                    )
                    if consumed.rowcount != 1:
                        return RegistrationInvalid()

                    row = (
                        await session.execute(
                            select(RegistrationChallengeRow)
                            .where(RegistrationChallengeRow.id == expected.id)
                            .with_for_update()
                        )
                    ).scalar_one_or_none()
                    if row is None:
                        raise RuntimeError("consumed registration challenge disappeared")

                    user = AppUser(
                        email=row.email,
                        password_hash=row.password_hash,
                        name=row.name,
                        role=Role.DESIGNER.value,
                    )
                    session.add(user)
                    await session.flush()
                    await session.refresh(user)
                    account = _to_account(user)
            return RegistrationCompleted(account)
        except IntegrityError as error:
            if _is_app_user_email_duplicate(error):
                return RegistrationDuplicate()
            raise
