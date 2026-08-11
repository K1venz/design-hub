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
from sqlalchemy.exc import IntegrityError, OperationalError
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
    _is_registration_claim_contention,
    _is_registration_email_duplicate,
)
from design_hub.ports.registration import (
    RegistrationClaimed,
    RegistrationCompleted,
    RegistrationDeliveryState,
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
    return IntegrityError("INSERT", {}, original)


def _operational_error(original: Exception) -> OperationalError:
    return OperationalError("UPDATE", {}, original)


@pytest.mark.parametrize(
    ("original", "classifier"),
    [
        (
            _AsyncpgError(
                'duplicate key value violates unique constraint "uq_app_user_email"\n',
                sqlstate="23505",
            ),
            _is_app_user_email_duplicate,
        ),
        (
            sqlite3.IntegrityError("UNIQUE constraint failed: app_user.email"),
            _is_app_user_email_duplicate,
        ),
        (
            _MySqlError(
                1062,
                "Duplicate entry 'redacted' for key 'app_user.uq_app_user_email'",
            ),
            _is_app_user_email_duplicate,
        ),
        (
            _AsyncpgError(
                "duplicate key value violates unique constraint "
                '"uq_registration_challenge_email"\n',
                sqlstate="23505",
            ),
            _is_registration_email_duplicate,
        ),
        (
            sqlite3.IntegrityError("UNIQUE constraint failed: registration_challenge.email"),
            _is_registration_email_duplicate,
        ),
        (
            _MySqlError(
                1062,
                "Duplicate entry 'redacted' for key "
                "'registration_challenge.uq_registration_challenge_email'",
            ),
            _is_registration_email_duplicate,
        ),
    ],
)
def test_duplicate_classifiers_accept_only_their_cross_database_target(
    original: Exception,
    classifier: Any,
) -> None:
    error = _integrity_error(original)

    assert classifier(error)
    assert not (
        _is_registration_email_duplicate(error)
        if classifier is _is_app_user_email_duplicate
        else _is_app_user_email_duplicate(error)
    )


@pytest.mark.parametrize(
    "original",
    [
        _AsyncpgError("serialization failure", sqlstate="40001"),
        _AsyncpgError("deadlock detected", sqlstate="40P01"),
        _MySqlError(1205, "Lock wait timeout exceeded"),
        _MySqlError(1213, "Deadlock found when trying to get lock"),
        sqlite3.OperationalError("database is locked"),
        sqlite3.OperationalError("database table is locked"),
    ],
)
def test_claim_contention_classifier_covers_supported_databases(original: Exception) -> None:
    assert _is_registration_claim_contention(_operational_error(original))


def test_duplicate_and_contention_classifiers_propagate_non_target_database_errors() -> None:
    composite = _integrity_error(
        sqlite3.IntegrityError("UNIQUE constraint failed: app_user.email, app_user.name")
    )
    near_match = _integrity_error(
        _MySqlError(
            1062,
            "Duplicate entry 'redacted' for key "
            "'registration_challenge.uq_registration_challenge_email_archive'",
        )
    )
    unrelated_lock = _operational_error(sqlite3.OperationalError("disk I/O error"))

    assert not _is_app_user_email_duplicate(composite)
    assert not _is_registration_email_duplicate(composite)
    assert not _is_registration_email_duplicate(near_match)
    assert not _is_registration_claim_contention(unrelated_lock)


def test_registration_timestamp_columns_compile_with_mysql_microseconds() -> None:
    dialect = mysql.dialect()
    columns = RegistrationChallengeRow.__table__.c
    names = (
        "expires_at",
        "created_at",
        "delivery_claimed_at",
        "activated_at",
        "consumed_at",
    )

    assert {name: columns[name].type.compile(dialect=dialect) for name in names} == {
        name: "DATETIME(6)" for name in names
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

    assert output.getvalue().count("DATETIME(6)") == 5


async def _database(
    path: Path | None = None,
) -> tuple[async_sessionmaker[AsyncSession], AsyncEngine]:
    url = "sqlite+aiosqlite:///:memory:"
    connect_args: dict[str, object] = {}
    if path is not None:
        url = f"sqlite+aiosqlite:///{path.as_posix()}"
        connect_args = {"autocommit": False, "timeout": 2.0}
    engine = create_async_engine(url, connect_args=connect_args)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def _active(
    store: SqlAlchemyRegistrationStore,
    *,
    email: str = "designer@example.com",
    claimed_at: datetime | None = None,
):
    claimed_at = claimed_at or datetime(2026, 8, 10, 2, 0, tzinfo=UTC)
    claim = await store.claim_initial(
        email=email,
        name="Pending Designer",
        password_hash="$2b$12$pending-password-hash",
        code_hash="a" * 64,
        expires_at=claimed_at + timedelta(minutes=10),
        claimed_at=claimed_at,
        cooldown_seconds=60,
    )
    assert isinstance(claim, RegistrationClaimed)
    active = await store.activate(
        challenge_id=claim.challenge.id,
        delivery_id=claim.challenge.delivery_id,
        activated_at=claimed_at + timedelta(seconds=1),
    )
    assert active is not None
    return active


def test_complete_atomically_creates_designer_and_consumes_active_delivery() -> None:
    async def scenario() -> None:
        sessions, engine = await _database()
        store = SqlAlchemyRegistrationStore(sessions)
        completed_at = datetime(2026, 8, 10, 2, 5, tzinfo=UTC)
        try:
            active = await _active(store)

            result = await store.complete(expected=active, completed_at=completed_at)

            assert isinstance(result, RegistrationCompleted)
            assert result.account.email == active.email
            assert result.account.name == active.name
            assert result.account.password_hash == active.password_hash
            assert result.account.role is Role.DESIGNER
            assert await store.get_active(email=active.email, challenge_id=active.id) is None
            async with sessions() as session:
                challenge = await session.get(RegistrationChallengeRow, active.id)
                users = (
                    (await session.execute(select(AppUser).where(AppUser.email == active.email)))
                    .scalars()
                    .all()
                )
            assert challenge is not None
            assert challenge.delivery_state == RegistrationDeliveryState.CONSUMED.value
            assert challenge.consumed_at == completed_at.replace(tzinfo=None)
            assert len(users) == 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_claim_returns_exact_utc_microseconds_used_by_completion() -> None:
    async def scenario() -> None:
        sessions, engine = await _database()
        store = SqlAlchemyRegistrationStore(sessions)
        local_timezone = timezone(timedelta(hours=5, minutes=30))
        claimed_at = datetime(
            2026,
            8,
            10,
            7,
            30,
            0,
            654321,
            tzinfo=local_timezone,
        )
        expires_at = datetime(
            2026,
            8,
            10,
            7,
            40,
            0,
            123456,
            tzinfo=local_timezone,
        )
        try:
            claim = await store.claim_initial(
                email="offset@example.com",
                name="Offset Designer",
                password_hash="$2b$12$offset-password-hash",
                code_hash="d" * 64,
                expires_at=expires_at,
                claimed_at=claimed_at,
                cooldown_seconds=60,
            )
            assert isinstance(claim, RegistrationClaimed)
            pending = claim.challenge

            assert pending.expires_at == datetime(2026, 8, 10, 2, 10, 0, 123456, tzinfo=UTC)
            assert pending.created_at == datetime(2026, 8, 10, 2, 0, 0, 654321, tzinfo=UTC)
            assert pending.delivery_claimed_at == pending.created_at
            async with sessions() as session:
                stored = await session.get(RegistrationChallengeRow, pending.id)
            assert stored is not None
            assert stored.expires_at == datetime(2026, 8, 10, 2, 10, 0, 123456)
            assert stored.delivery_claimed_at == datetime(2026, 8, 10, 2, 0, 0, 654321)
        finally:
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "stale_state",
    [
        {"code_hash": "c" * 64},
        {"attempt_count": 1},
        {"delivery_id": "stale-delivery-id"},
    ],
)
def test_complete_rejects_stale_service_snapshot_without_partial_state(
    stale_state: dict[str, object],
) -> None:
    async def scenario() -> None:
        sessions, engine = await _database()
        store = SqlAlchemyRegistrationStore(sessions)
        try:
            active = await _active(store)
            result = await store.complete(
                expected=replace(active, **stale_state),
                completed_at=datetime(2026, 8, 10, 2, 5, tzinfo=UTC),
            )

            assert isinstance(result, RegistrationInvalid)
            assert await store.get_active(email=active.email, challenge_id=active.id) == active
            async with sessions() as session:
                user_count = await session.scalar(select(func.count()).select_from(AppUser))
            assert user_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_complete_rejects_pending_and_expired_challenges() -> None:
    async def scenario() -> None:
        sessions, engine = await _database()
        store = SqlAlchemyRegistrationStore(sessions)
        try:
            claimed_at = datetime(2026, 8, 10, 2, 0, tzinfo=UTC)
            claim = await store.claim_initial(
                email="pending@example.com",
                name="Pending",
                password_hash="hash",
                code_hash="a" * 64,
                expires_at=claimed_at + timedelta(minutes=10),
                claimed_at=claimed_at,
                cooldown_seconds=60,
            )
            assert isinstance(claim, RegistrationClaimed)
            assert isinstance(
                await store.complete(expected=claim.challenge, completed_at=claimed_at),
                RegistrationInvalid,
            )

            active = await _active(store, email="expired@example.com")
            assert isinstance(
                await store.complete(expected=active, completed_at=active.expires_at),
                RegistrationInvalid,
            )
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_complete_duplicate_rolls_back_challenge_consumption() -> None:
    async def scenario() -> None:
        sessions, engine = await _database()
        store = SqlAlchemyRegistrationStore(sessions)
        try:
            active = await _active(store)
            async with sessions.begin() as session:
                session.add(
                    AppUser(
                        email=active.email,
                        password_hash="existing-hash",
                        name="Existing",
                        role=Role.DESIGNER.value,
                    )
                )

            result = await store.complete(
                expected=active,
                completed_at=datetime(2026, 8, 10, 2, 5, tzinfo=UTC),
            )

            assert isinstance(result, RegistrationDuplicate)
            assert await store.get_active(email=active.email, challenge_id=active.id) == active
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_complete_propagates_unrelated_integrity_error() -> None:
    async def scenario() -> None:
        sessions, engine = await _database()
        store = SqlAlchemyRegistrationStore(sessions)
        try:
            active = await _active(store)
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
                    expected=active,
                    completed_at=datetime(2026, 8, 10, 2, 5, tzinfo=UTC),
                )
            assert await store.get_active(email=active.email, challenge_id=active.id) == active
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_two_concurrent_completions_create_exactly_one_user(tmp_path: Path) -> None:
    async def scenario() -> None:
        sessions, engine = await _database(tmp_path / "registration-completion.db")
        store = SqlAlchemyRegistrationStore(sessions)
        try:
            active = await _active(store)
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

            racing_store = SqlAlchemyRegistrationStore(
                async_sessionmaker(engine, class_=RacingSession, expire_on_commit=False)
            )
            first, second = await asyncio.gather(
                racing_store.complete(expected=active, completed_at=completed_at),
                racing_store.complete(expected=active, completed_at=completed_at),
            )

            assert sum(isinstance(result, RegistrationCompleted) for result in (first, second)) == 1
            assert sum(isinstance(result, RegistrationInvalid) for result in (first, second)) == 1
            async with sessions() as session:
                user_count = await session.scalar(
                    select(func.count()).select_from(AppUser).where(AppUser.email == active.email)
                )
            assert user_count == 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())
