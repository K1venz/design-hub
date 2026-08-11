"""Atomic SQLAlchemy store for password-reset delivery and completion."""

import math
import re
import secrets
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.infrastructure.db.models import AppUser, PasswordResetChallengeRow
from design_hub.ports.password_reset import (
    PasswordResetAccountUnavailable,
    PasswordResetAttemptsExceeded,
    PasswordResetChallenge,
    PasswordResetClaim,
    PasswordResetClaimContended,
    PasswordResetClaimed,
    PasswordResetCompleted,
    PasswordResetCompletion,
    PasswordResetCooldown,
    PasswordResetDeliveryState,
    PasswordResetInvalid,
    PasswordResetStore,
)

_PASSWORD_RESET_EMAIL_CONSTRAINT = "uq_password_reset_challenge_email"
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


class _AccountUnavailable(Exception):
    pass


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _new_id() -> str:
    return secrets.token_urlsafe(32)


def _to_challenge(row: PasswordResetChallengeRow) -> PasswordResetChallenge:
    return PasswordResetChallenge(
        id=row.id,
        delivery_id=row.delivery_id,
        email=row.email,
        code_hash=row.code_hash,
        delivery_state=PasswordResetDeliveryState(row.delivery_state),
        expires_at=_utc(row.expires_at),
        attempt_count=row.attempt_count,
        created_at=_utc(row.created_at),
        delivery_claimed_at=_utc(row.delivery_claimed_at),
        activated_at=_utc(row.activated_at) if row.activated_at is not None else None,
        consumed_at=_utc(row.consumed_at) if row.consumed_at is not None else None,
    )


def _cooldown_remaining(
    *,
    previous_claimed_at: datetime,
    claimed_at: datetime,
    cooldown_seconds: int,
) -> int:
    age = (_utc(claimed_at) - _utc(previous_claimed_at)).total_seconds()
    return max(0, math.ceil(cooldown_seconds - age))


def _is_password_reset_email_duplicate(error: IntegrityError) -> bool:
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
        if constraint is None:
            match = _POSTGRES_UNIQUE_CONSTRAINT.search(str(original))
            constraint = match.group("constraint") if match is not None else None
        return constraint == _PASSWORD_RESET_EMAIL_CONSTRAINT
    if isinstance(original, sqlite3.IntegrityError):
        return (
            str(original).strip().casefold()
            == "unique constraint failed: password_reset_challenge.email"
        )
    if not args or args[0] != 1062 or len(args) < 2 or not isinstance(args[1], str):
        return False
    match = _MYSQL_DUPLICATE_KEY.search(args[1])
    if match is None:
        return False
    return match.group("constraint").rsplit(".", maxsplit=1)[-1] == _PASSWORD_RESET_EMAIL_CONSTRAINT


def _is_password_reset_claim_contention(error: DBAPIError) -> bool:
    if isinstance(error, IntegrityError) and _is_password_reset_email_duplicate(error):
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


class SqlAlchemyPasswordResetStore(PasswordResetStore):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def claim(
        self,
        *,
        email: str,
        code_hash: str,
        expires_at: datetime,
        claimed_at: datetime,
        cooldown_seconds: int,
    ) -> PasswordResetClaim:
        claimed_at_utc = _utc(claimed_at)
        expires_at_utc = _utc(expires_at)
        challenge_id = _new_id()
        delivery_id = _new_id()
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    enabled = await session.scalar(
                        select(AppUser.enabled).where(AppUser.email == email)
                    )
                    if enabled is not True:
                        return PasswordResetAccountUnavailable()

                    row = (
                        await session.execute(
                            select(PasswordResetChallengeRow)
                            .where(PasswordResetChallengeRow.email == email)
                            .with_for_update()
                        )
                    ).scalar_one_or_none()
                    if row is not None:
                        if (
                            row.delivery_state == PasswordResetDeliveryState.PENDING.value
                            and _utc(row.expires_at) > claimed_at_utc
                        ):
                            retry_after = max(
                                1,
                                math.ceil(
                                    (_utc(row.expires_at) - claimed_at_utc).total_seconds()
                                ),
                            )
                            return PasswordResetClaimContended(retry_after)
                        remaining = _cooldown_remaining(
                            previous_claimed_at=row.delivery_claimed_at,
                            claimed_at=claimed_at_utc,
                            cooldown_seconds=cooldown_seconds,
                        )
                        if (
                            row.delivery_state == PasswordResetDeliveryState.ACTIVE.value
                            and remaining > 0
                        ):
                            return PasswordResetCooldown(remaining)
                        row.id = challenge_id
                        row.delivery_id = delivery_id
                        row.code_hash = code_hash
                        row.delivery_state = PasswordResetDeliveryState.PENDING.value
                        row.expires_at = expires_at_utc
                        row.attempt_count = 0
                        row.created_at = claimed_at_utc
                        row.delivery_claimed_at = claimed_at_utc
                        row.activated_at = None
                        row.consumed_at = None
                    else:
                        row = PasswordResetChallengeRow(
                            id=challenge_id,
                            delivery_id=delivery_id,
                            email=email,
                            code_hash=code_hash,
                            delivery_state=PasswordResetDeliveryState.PENDING.value,
                            expires_at=expires_at_utc,
                            attempt_count=0,
                            created_at=claimed_at_utc,
                            delivery_claimed_at=claimed_at_utc,
                            activated_at=None,
                            consumed_at=None,
                        )
                        session.add(row)
                    await session.flush()
                    return PasswordResetClaimed(_to_challenge(row))
        except DBAPIError as error:
            if _is_password_reset_claim_contention(error):
                return PasswordResetClaimContended()
            raise

    async def activate(
        self,
        *,
        challenge_id: str,
        delivery_id: str,
        activated_at: datetime,
    ) -> PasswordResetChallenge | None:
        activated_at_utc = _utc(activated_at)
        async with self._session_factory() as session:
            async with session.begin():
                result = cast(
                    CursorResult[Any],
                    await session.execute(
                        update(PasswordResetChallengeRow)
                        .where(
                            PasswordResetChallengeRow.id == challenge_id,
                            PasswordResetChallengeRow.delivery_id == delivery_id,
                            PasswordResetChallengeRow.delivery_state
                            == PasswordResetDeliveryState.PENDING.value,
                            PasswordResetChallengeRow.expires_at > activated_at_utc,
                            PasswordResetChallengeRow.consumed_at.is_(None),
                        )
                        .values(
                            delivery_state=PasswordResetDeliveryState.ACTIVE.value,
                            activated_at=activated_at_utc,
                        )
                    ),
                )
                if result.rowcount != 1:
                    return None
                row = await session.get(PasswordResetChallengeRow, challenge_id)
                if row is None:
                    raise RuntimeError("activated password-reset challenge disappeared")
                return _to_challenge(row)

    async def get_active(self, *, email: str) -> PasswordResetChallenge | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(PasswordResetChallengeRow).where(
                        PasswordResetChallengeRow.email == email,
                        PasswordResetChallengeRow.delivery_state
                        == PasswordResetDeliveryState.ACTIVE.value,
                        PasswordResetChallengeRow.consumed_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            return _to_challenge(row) if row is not None else None

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
                        update(PasswordResetChallengeRow)
                        .where(
                            PasswordResetChallengeRow.id == challenge_id,
                            PasswordResetChallengeRow.delivery_id == delivery_id,
                            PasswordResetChallengeRow.consumed_at.is_(None),
                        )
                        .values(
                            delivery_state=PasswordResetDeliveryState.CONSUMED.value,
                            consumed_at=invalidated_at_utc,
                        )
                    ),
                )
                return result.rowcount == 1

    async def complete(
        self,
        *,
        email: str,
        code_hash: str,
        password_hash_factory: Callable[[], str],
        completed_at: datetime,
        max_attempts: int,
    ) -> PasswordResetCompletion:
        completed_at_utc = _utc(completed_at)
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    consumed = cast(
                        CursorResult[Any],
                        await session.execute(
                            update(PasswordResetChallengeRow)
                            .where(
                                PasswordResetChallengeRow.email == email,
                                PasswordResetChallengeRow.code_hash == code_hash,
                                PasswordResetChallengeRow.delivery_state
                                == PasswordResetDeliveryState.ACTIVE.value,
                                PasswordResetChallengeRow.expires_at > completed_at_utc,
                                PasswordResetChallengeRow.attempt_count < max_attempts,
                                PasswordResetChallengeRow.consumed_at.is_(None),
                            )
                            .values(
                                delivery_state=PasswordResetDeliveryState.CONSUMED.value,
                                consumed_at=completed_at_utc,
                            )
                        ),
                    )
                    if consumed.rowcount == 1:
                        user = (
                            await session.execute(
                                select(AppUser)
                                .where(
                                    AppUser.email == email,
                                    AppUser.enabled.is_(True),
                                )
                                .with_for_update()
                            )
                        ).scalar_one_or_none()
                        if user is None:
                            raise _AccountUnavailable
                        user.password_hash = password_hash_factory()
                        return PasswordResetCompleted()

                    failed = cast(
                        CursorResult[Any],
                        await session.execute(
                            update(PasswordResetChallengeRow)
                            .where(
                                PasswordResetChallengeRow.email == email,
                                PasswordResetChallengeRow.code_hash != code_hash,
                                PasswordResetChallengeRow.delivery_state
                                == PasswordResetDeliveryState.ACTIVE.value,
                                PasswordResetChallengeRow.expires_at > completed_at_utc,
                                PasswordResetChallengeRow.attempt_count < max_attempts,
                                PasswordResetChallengeRow.consumed_at.is_(None),
                            )
                            .values(
                                attempt_count=PasswordResetChallengeRow.attempt_count + 1
                            )
                        ),
                    )
                    row = (
                        await session.execute(
                            select(PasswordResetChallengeRow).where(
                                PasswordResetChallengeRow.email == email
                            )
                        )
                    ).scalar_one_or_none()
                    if row is not None and row.attempt_count >= max_attempts:
                        return PasswordResetAttemptsExceeded()
                    if failed.rowcount not in (0, 1):
                        raise RuntimeError("unexpected password-reset attempt update count")
                    return PasswordResetInvalid()
        except _AccountUnavailable:
            return PasswordResetInvalid()
