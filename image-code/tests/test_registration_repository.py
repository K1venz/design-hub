from __future__ import annotations

import asyncio
import importlib
import io
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, select, text
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from design_hub.domain.enums import Role
from design_hub.infrastructure.db.base import Base
from design_hub.infrastructure.db.models import AppUser, RegistrationChallengeRow
from design_hub.infrastructure.db.registration_repo import (
    SqlAlchemyRegistrationStore,
    _is_app_user_email_duplicate,
)
from design_hub.ports.registration import (
    RegistrationCompleted,
    RegistrationDuplicate,
    RegistrationInvalid,
)


class _AsyncpgError(Exception):
    def __init__(self, message: str, *, sqlstate: str) -> None:
        super().__init__(message)
        self.sqlstate = sqlstate


class _MySqlError(Exception):
    pass


def _integrity_error(original: Exception) -> IntegrityError:
    return IntegrityError("INSERT INTO app_user", {}, original)


def test_duplicate_classifier_recognizes_asyncpg_target_constraint_without_diag() -> None:
    original = _AsyncpgError(
        "<class 'asyncpg.exceptions.UniqueViolationError'>: "
        'duplicate key value violates unique constraint "uq_app_user_email"\n'
        "DETAIL: Key (email)=(redacted) already exists.",
        sqlstate="23505",
    )

    assert _is_app_user_email_duplicate(_integrity_error(original))


def test_duplicate_classifier_rejects_asyncpg_non_target_constraint() -> None:
    original = _AsyncpgError(
        "<class 'asyncpg.exceptions.UniqueViolationError'>: "
        'duplicate key value violates unique constraint "uq_app_user_name"\n'
        "DETAIL: Key (name)=(redacted) already exists.",
        sqlstate="23505",
    )

    assert not _is_app_user_email_duplicate(_integrity_error(original))


def test_duplicate_classifier_rejects_sqlite_composite_unique_constraint() -> None:
    original = sqlite3.IntegrityError("UNIQUE constraint failed: app_user.email, app_user.name")

    assert not _is_app_user_email_duplicate(_integrity_error(original))


def test_duplicate_classifier_requires_the_exact_mysql_constraint_name() -> None:
    target = _MySqlError(
        1062,
        "Duplicate entry 'redacted' for key 'app_user.uq_app_user_email'",
    )
    near_match = _MySqlError(
        1062,
        "Duplicate entry 'redacted' for key 'app_user.uq_app_user_email_archive'",
    )

    assert _is_app_user_email_duplicate(_integrity_error(target))
    assert not _is_app_user_email_duplicate(_integrity_error(near_match))


def test_registration_timestamp_columns_compile_with_mysql_microseconds() -> None:
    dialect = mysql.dialect()
    columns = RegistrationChallengeRow.__table__.c

    assert {
        name: columns[name].type.compile(dialect=dialect)
        for name in ("expires_at", "created_at", "last_sent_at", "consumed_at")
    } == {
        "expires_at": "DATETIME(6)",
        "created_at": "DATETIME(6)",
        "last_sent_at": "DATETIME(6)",
        "consumed_at": "DATETIME(6)",
    }


def test_registration_migration_emits_mysql_microsecond_timestamps() -> None:
    migration_path = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "b9c0d1e2f3a4_registration_challenge.py"
    )
    specification = importlib.util.spec_from_file_location(
        "registration_challenge_migration",
        migration_path,
    )
    assert specification is not None
    assert specification.loader is not None
    migration = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(migration)
    output = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="mysql",
        opts={"as_sql": True, "output_buffer": output},
    )

    with Operations.context(context):
        migration.upgrade()

    assert output.getvalue().count("DATETIME(6)") == 4


async def _database(
    path: Path | None = None,
) -> tuple[async_sessionmaker[AsyncSession], AsyncEngine]:
    url = "sqlite+aiosqlite:///:memory:"
    if path is not None:
        url = f"sqlite+aiosqlite:///{path.as_posix()}"
    connect_args = {"autocommit": False, "timeout": 0.2} if path is not None else {}
    engine = create_async_engine(url, connect_args=connect_args)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def _pending(
    store: SqlAlchemyRegistrationStore,
    *,
    email: str = "designer@example.com",
    sent_at: datetime | None = None,
):
    sent_at = sent_at or datetime(2026, 8, 10, 2, 0, tzinfo=UTC)
    return await store.replace_active(
        email=email,
        name="Pending Designer",
        password_hash="$2b$12$pending-password-hash",
        code_hash="a" * 64,
        expires_at=sent_at + timedelta(minutes=10),
        sent_at=sent_at,
    )


def test_replace_active_reuses_the_unique_email_row_and_resets_challenge_state() -> None:
    async def scenario() -> None:
        sessions, engine = await _database()
        store = SqlAlchemyRegistrationStore(sessions)
        first_sent_at = datetime(2026, 8, 10, 2, 0, tzinfo=UTC)
        second_sent_at = first_sent_at + timedelta(minutes=2)
        try:
            first = await _pending(store, sent_at=first_sent_at)
            failed = await store.record_failed_attempt(first.id)
            assert failed is not None
            assert failed.attempt_count == 1

            second = await store.replace_active(
                email="designer@example.com",
                name="Updated Designer",
                password_hash="$2b$12$updated-password-hash",
                code_hash="b" * 64,
                expires_at=second_sent_at + timedelta(minutes=10),
                sent_at=second_sent_at,
            )

            assert second.id != first.id
            assert second.email == "designer@example.com"
            assert second.name == "Updated Designer"
            assert second.password_hash == "$2b$12$updated-password-hash"
            assert second.code_hash == "b" * 64
            assert second.attempt_count == 0
            assert second.created_at == first_sent_at
            assert second.last_sent_at == second_sent_at
            assert second.consumed_at is None
            assert await store.get_active("designer@example.com") == second

            async with sessions() as session:
                row_count = await session.scalar(
                    select(func.count()).select_from(RegistrationChallengeRow)
                )
            assert row_count == 1
            assert await store.record_failed_attempt(first.id) is None
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_invalidate_hides_the_current_challenge_without_deleting_it() -> None:
    async def scenario() -> None:
        sessions, engine = await _database()
        store = SqlAlchemyRegistrationStore(sessions)
        invalidated_at = datetime(2026, 8, 10, 2, 3, tzinfo=UTC)
        try:
            pending = await _pending(store)
            await store.invalidate(
                challenge_id=pending.id,
                invalidated_at=invalidated_at,
            )

            assert await store.get_active(pending.email) is None
            async with sessions() as session:
                row = await session.get(RegistrationChallengeRow, pending.id)
            assert row is not None
            assert row.consumed_at is not None
            assert row.consumed_at.replace(tzinfo=UTC) == invalidated_at
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_record_failed_attempt_increments_only_the_current_unconsumed_challenge() -> None:
    async def scenario() -> None:
        sessions, engine = await _database()
        store = SqlAlchemyRegistrationStore(sessions)
        try:
            pending = await _pending(store)

            first = await store.record_failed_attempt(pending.id)
            second = await store.record_failed_attempt(pending.id)

            assert first is not None
            assert first.attempt_count == 1
            assert second is not None
            assert second.attempt_count == 2

            await store.invalidate(
                challenge_id=pending.id,
                invalidated_at=datetime(2026, 8, 10, 2, 4, tzinfo=UTC),
            )
            assert await store.record_failed_attempt(pending.id) is None
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_complete_atomically_creates_a_designer_and_consumes_the_challenge() -> None:
    async def scenario() -> None:
        sessions, engine = await _database()
        store = SqlAlchemyRegistrationStore(sessions)
        completed_at = datetime(2026, 8, 10, 2, 5, tzinfo=UTC)
        try:
            pending = await _pending(store)

            result = await store.complete(expected=pending, completed_at=completed_at)

            assert isinstance(result, RegistrationCompleted)
            assert result.account.email == pending.email
            assert result.account.name == pending.name
            assert result.account.password_hash == pending.password_hash
            assert result.account.role is Role.DESIGNER
            assert await store.get_active(pending.email) is None

            async with sessions() as session:
                challenge = await session.get(RegistrationChallengeRow, pending.id)
                users = (
                    (await session.execute(select(AppUser).where(AppUser.email == pending.email)))
                    .scalars()
                    .all()
                )
            assert challenge is not None
            assert challenge.consumed_at is not None
            assert challenge.consumed_at.replace(tzinfo=UTC) == completed_at
            assert len(users) == 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_replace_returns_the_utc_microsecond_snapshot_used_by_complete() -> None:
    async def scenario() -> None:
        sessions, engine = await _database()
        store = SqlAlchemyRegistrationStore(sessions)
        local_timezone = timezone(timedelta(hours=5, minutes=30))
        try:
            pending = await store.replace_active(
                email="offset@example.com",
                name="Offset Designer",
                password_hash="$2b$12$offset-password-hash",
                code_hash="d" * 64,
                expires_at=datetime(
                    2026,
                    8,
                    10,
                    7,
                    40,
                    0,
                    123456,
                    tzinfo=local_timezone,
                ),
                sent_at=datetime(
                    2026,
                    8,
                    10,
                    7,
                    30,
                    0,
                    654321,
                    tzinfo=local_timezone,
                ),
            )

            assert pending.expires_at == datetime(2026, 8, 10, 2, 10, 0, 123456, tzinfo=UTC)
            assert pending.created_at == datetime(2026, 8, 10, 2, 0, 0, 654321, tzinfo=UTC)
            assert pending.last_sent_at == datetime(2026, 8, 10, 2, 0, 0, 654321, tzinfo=UTC)
            async with sessions() as session:
                stored = await session.get(RegistrationChallengeRow, pending.id)
            assert stored is not None
            assert stored.expires_at == datetime(2026, 8, 10, 2, 10, 0, 123456)
            assert stored.created_at == datetime(2026, 8, 10, 2, 0, 0, 654321)
            assert stored.last_sent_at == datetime(2026, 8, 10, 2, 0, 0, 654321)

            result = await store.complete(
                expected=pending,
                completed_at=datetime(
                    2026,
                    8,
                    10,
                    7,
                    35,
                    0,
                    777888,
                    tzinfo=local_timezone,
                ),
            )

            assert isinstance(result, RegistrationCompleted)
            async with sessions() as session:
                consumed = await session.get(RegistrationChallengeRow, pending.id)
            assert consumed is not None
            assert consumed.consumed_at == datetime(2026, 8, 10, 2, 5, 0, 777888)
        finally:
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "stale_state",
    [
        {"code_hash": "c" * 64},
        {"attempt_count": 1},
    ],
)
def test_complete_rejects_a_stale_service_snapshot_without_partial_state(
    stale_state: dict[str, object],
) -> None:
    async def scenario() -> None:
        sessions, engine = await _database()
        store = SqlAlchemyRegistrationStore(sessions)
        try:
            pending = await _pending(store)
            result = await store.complete(
                expected=replace(pending, **stale_state),
                completed_at=datetime(2026, 8, 10, 2, 5, tzinfo=UTC),
            )

            assert isinstance(result, RegistrationInvalid)
            assert await store.get_active(pending.email) == pending
            async with sessions() as session:
                user_count = await session.scalar(select(func.count()).select_from(AppUser))
            assert user_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_complete_rejects_an_expired_challenge_without_partial_state() -> None:
    async def scenario() -> None:
        sessions, engine = await _database()
        store = SqlAlchemyRegistrationStore(sessions)
        try:
            pending = await _pending(store)
            result = await store.complete(
                expected=pending,
                completed_at=pending.expires_at,
            )

            assert isinstance(result, RegistrationInvalid)
            assert await store.get_active(pending.email) == pending
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_complete_returns_duplicate_and_rolls_back_consumption_for_an_existing_user() -> None:
    async def scenario() -> None:
        sessions, engine = await _database()
        store = SqlAlchemyRegistrationStore(sessions)
        try:
            pending = await _pending(store)
            async with sessions.begin() as session:
                session.add(
                    AppUser(
                        email=pending.email,
                        password_hash="$2b$12$existing-password-hash",
                        name="Existing Designer",
                        role=Role.DESIGNER.value,
                    )
                )

            result = await store.complete(
                expected=pending,
                completed_at=datetime(2026, 8, 10, 2, 5, tzinfo=UTC),
            )

            assert isinstance(result, RegistrationDuplicate)
            assert await store.get_active(pending.email) == pending
            async with sessions() as session:
                user_count = await session.scalar(select(func.count()).select_from(AppUser))
            assert user_count == 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_complete_does_not_translate_an_unrelated_integrity_error() -> None:
    async def scenario() -> None:
        sessions, engine = await _database()
        store = SqlAlchemyRegistrationStore(sessions)
        try:
            pending = await _pending(store)
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        """
                        CREATE TRIGGER reject_app_user_insert
                        BEFORE INSERT ON app_user
                        BEGIN
                            SELECT RAISE(ABORT, 'unrelated integrity failure');
                        END
                        """
                    )
                )

            with pytest.raises(IntegrityError, match="unrelated integrity failure"):
                await store.complete(
                    expected=pending,
                    completed_at=datetime(2026, 8, 10, 2, 5, tzinfo=UTC),
                )

            assert await store.get_active(pending.email) == pending
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_two_concurrent_completions_create_exactly_one_user(tmp_path: Path) -> None:
    async def scenario() -> None:
        sessions, engine = await _database(tmp_path / "registration-concurrency.db")
        store = SqlAlchemyRegistrationStore(sessions)
        try:
            pending = await _pending(store)
            completed_at = datetime(2026, 8, 10, 2, 5, tzinfo=UTC)
            cas_start = asyncio.Barrier(2)

            class RacingSession(AsyncSession):
                async def execute(
                    self,
                    statement: Any,
                    *args: Any,
                    **kwargs: Any,
                ) -> Any:
                    if (
                        getattr(statement, "is_update", False)
                        and getattr(getattr(statement, "table", None), "name", None)
                        == "registration_challenge"
                    ):
                        await cas_start.wait()
                    return await super().execute(statement, *args, **kwargs)

            racing_sessions = async_sessionmaker(
                engine,
                class_=RacingSession,
                expire_on_commit=False,
            )
            racing_store = SqlAlchemyRegistrationStore(racing_sessions)

            first, second = await asyncio.gather(
                racing_store.complete(expected=pending, completed_at=completed_at),
                racing_store.complete(expected=pending, completed_at=completed_at),
            )

            assert sum(isinstance(result, RegistrationCompleted) for result in (first, second)) == 1
            assert sum(isinstance(result, RegistrationInvalid) for result in (first, second)) == 1
            async with sessions() as session:
                user_count = await session.scalar(
                    select(func.count()).select_from(AppUser).where(AppUser.email == pending.email)
                )
                challenge = await session.get(RegistrationChallengeRow, pending.id)
            assert user_count == 1
            assert challenge is not None
            assert challenge.consumed_at is not None
        finally:
            await engine.dispose()

    asyncio.run(scenario())
