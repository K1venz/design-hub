"""SQLAlchemy store for pending registrations."""

from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.enums import Role
from design_hub.infrastructure.db.models import AppUser, RegistrationChallengeRow
from design_hub.ports.registration import (
    PendingRegistration,
    RegistrationCompleted,
    RegistrationCompletion,
    RegistrationDuplicate,
    RegistrationInvalid,
    RegistrationStore,
)
from design_hub.ports.user_repository import UserAccount


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_challenge(row: RegistrationChallengeRow) -> PendingRegistration:
    return PendingRegistration(
        id=row.id,
        email=row.email,
        name=row.name,
        password_hash=row.password_hash,
        code_hash=row.code_hash,
        expires_at=_utc(row.expires_at),
        attempt_count=row.attempt_count,
        created_at=_utc(row.created_at),
        last_sent_at=_utc(row.last_sent_at),
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


def _is_app_user_email_duplicate(error: IntegrityError) -> bool:
    original: Any = error.orig
    diagnostic = getattr(original, "diag", None)
    if getattr(diagnostic, "constraint_name", None) == "uq_app_user_email":
        return True

    message = str(original).lower()
    if "unique constraint failed: app_user.email" in message:
        return True

    args = getattr(original, "args", ())
    error_code = args[0] if args else None
    return error_code == 1062 and "uq_app_user_email" in message


class SqlAlchemyRegistrationStore(RegistrationStore):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_active(self, email: str) -> PendingRegistration | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(RegistrationChallengeRow).where(
                        RegistrationChallengeRow.email == email,
                        RegistrationChallengeRow.consumed_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            return _to_challenge(row) if row is not None else None

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
        async with self._session_factory() as session:
            async with session.begin():
                row = (
                    await session.execute(
                        select(RegistrationChallengeRow)
                        .where(RegistrationChallengeRow.email == email)
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                challenge_id = uuid4().hex
                if row is None:
                    row = RegistrationChallengeRow(
                        id=challenge_id,
                        email=email,
                        name=name,
                        password_hash=password_hash,
                        code_hash=code_hash,
                        expires_at=expires_at,
                        attempt_count=0,
                        created_at=sent_at,
                        last_sent_at=sent_at,
                        consumed_at=None,
                    )
                    session.add(row)
                else:
                    was_active = row.consumed_at is None
                    row.id = challenge_id
                    row.name = name
                    row.password_hash = password_hash
                    row.code_hash = code_hash
                    row.expires_at = expires_at
                    row.attempt_count = 0
                    if not was_active:
                        row.created_at = sent_at
                    row.last_sent_at = sent_at
                    row.consumed_at = None
                await session.flush()
                return _to_challenge(row)

    async def record_failed_attempt(self, challenge_id: str) -> PendingRegistration | None:
        async with self._session_factory() as session:
            async with session.begin():
                result = cast(
                    CursorResult[Any],
                    await session.execute(
                        update(RegistrationChallengeRow)
                        .where(
                            RegistrationChallengeRow.id == challenge_id,
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

    async def invalidate(self, *, challenge_id: str, invalidated_at: datetime) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(RegistrationChallengeRow)
                    .where(
                        RegistrationChallengeRow.id == challenge_id,
                        RegistrationChallengeRow.consumed_at.is_(None),
                    )
                    .values(consumed_at=invalidated_at)
                )

    async def complete(
        self,
        *,
        expected: PendingRegistration,
        completed_at: datetime,
    ) -> RegistrationCompletion:
        if expected.consumed_at is not None or _utc(expected.expires_at) <= _utc(completed_at):
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
                                RegistrationChallengeRow.email == expected.email,
                                RegistrationChallengeRow.code_hash == expected.code_hash,
                                RegistrationChallengeRow.expires_at == expected.expires_at,
                                RegistrationChallengeRow.expires_at > completed_at,
                                RegistrationChallengeRow.attempt_count == expected.attempt_count,
                                RegistrationChallengeRow.consumed_at.is_(None),
                            )
                            .values(consumed_at=completed_at)
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
