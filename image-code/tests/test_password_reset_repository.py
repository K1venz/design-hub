from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from design_hub.infrastructure.db.base import Base
from design_hub.infrastructure.db.models import AppUser
from design_hub.infrastructure.db.password_reset_repo import SqlAlchemyPasswordResetStore
from design_hub.ports.password_reset import (
    PasswordResetClaimContended,
    PasswordResetClaimed,
    PasswordResetCompleted,
    PasswordResetCooldown,
    PasswordResetInvalid,
)


async def _database(path: Path) -> tuple[async_sessionmaker[AsyncSession], AsyncEngine]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path.as_posix()}",
        connect_args={"autocommit": False, "timeout": 2.0},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def _seed_user(factory: async_sessionmaker[AsyncSession], *, email: str) -> None:
    async with factory() as session:
        async with session.begin():
            session.add(
                AppUser(
                    email=email,
                    password_hash="old-password-hash",
                    name="Reset User",
                    role="设计师",
                )
            )


async def _claim_and_activate(
    store: SqlAlchemyPasswordResetStore,
    *,
    email: str,
    code_hash: str,
    now: datetime,
):
    claim = await store.claim(
        email=email,
        code_hash=code_hash,
        expires_at=now + timedelta(minutes=10),
        claimed_at=now,
        cooldown_seconds=60,
    )
    assert isinstance(claim, PasswordResetClaimed)
    assert await store.get_active(email=email) is None
    active = await store.activate(
        challenge_id=claim.challenge.id,
        delivery_id=claim.challenge.delivery_id,
        activated_at=now,
    )
    assert active is not None
    return active


def test_concurrent_password_reset_claims_have_one_delivery_winner(tmp_path: Path) -> None:
    async def run() -> None:
        factory, engine = await _database(tmp_path / "claim.db")
        try:
            await _seed_user(factory, email="claim@example.com")
            stores = (
                SqlAlchemyPasswordResetStore(factory),
                SqlAlchemyPasswordResetStore(factory),
            )
            now = datetime.now(UTC)
            gate = asyncio.Event()

            async def claim(store: SqlAlchemyPasswordResetStore, code_hash: str):
                await gate.wait()
                return await store.claim(
                    email="claim@example.com",
                    code_hash=code_hash,
                    expires_at=now + timedelta(minutes=10),
                    claimed_at=now,
                    cooldown_seconds=60,
                )

            tasks = [
                asyncio.create_task(claim(stores[0], "a" * 64)),
                asyncio.create_task(claim(stores[1], "b" * 64)),
            ]
            gate.set()
            outcomes = await asyncio.gather(*tasks)

            assert sum(isinstance(item, PasswordResetClaimed) for item in outcomes) == 1
            assert sum(
                isinstance(item, PasswordResetCooldown | PasswordResetClaimContended)
                for item in outcomes
            ) == 1
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_password_reset_is_not_verifiable_until_delivery_activation(tmp_path: Path) -> None:
    async def run() -> None:
        factory, engine = await _database(tmp_path / "activation.db")
        try:
            await _seed_user(factory, email="activation@example.com")
            store = SqlAlchemyPasswordResetStore(factory)
            now = datetime.now(UTC)
            claim = await store.claim(
                email="activation@example.com",
                code_hash="a" * 64,
                expires_at=now + timedelta(minutes=10),
                claimed_at=now,
                cooldown_seconds=60,
            )
            assert isinstance(claim, PasswordResetClaimed)

            assert await store.get_active(email="activation@example.com") is None
            assert await store.activate(
                challenge_id=claim.challenge.id,
                delivery_id=claim.challenge.delivery_id,
                activated_at=now,
            ) is not None
            assert await store.get_active(email="activation@example.com") is not None
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_pending_password_reset_delivery_cannot_be_reclaimed_after_resend_cooldown(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        factory, engine = await _database(tmp_path / "pending-claim.db")
        try:
            await _seed_user(factory, email="pending@example.com")
            store = SqlAlchemyPasswordResetStore(factory)
            now = datetime.now(UTC)
            first = await store.claim(
                email="pending@example.com",
                code_hash="a" * 64,
                expires_at=now + timedelta(minutes=10),
                claimed_at=now,
                cooldown_seconds=60,
            )
            assert isinstance(first, PasswordResetClaimed)

            second = await store.claim(
                email="pending@example.com",
                code_hash="b" * 64,
                expires_at=now + timedelta(minutes=11, seconds=1),
                claimed_at=now + timedelta(seconds=61),
                cooldown_seconds=60,
            )

            assert isinstance(second, PasswordResetClaimContended)
            assert await store.activate(
                challenge_id=first.challenge.id,
                delivery_id=first.challenge.delivery_id,
                activated_at=now + timedelta(seconds=62),
            ) is not None
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_expired_pending_password_reset_delivery_can_be_reclaimed(tmp_path: Path) -> None:
    async def run() -> None:
        factory, engine = await _database(tmp_path / "expired-pending.db")
        try:
            await _seed_user(factory, email="expired-pending@example.com")
            store = SqlAlchemyPasswordResetStore(factory)
            now = datetime.now(UTC)
            first = await store.claim(
                email="expired-pending@example.com",
                code_hash="a" * 64,
                expires_at=now + timedelta(minutes=10),
                claimed_at=now,
                cooldown_seconds=60,
            )
            assert isinstance(first, PasswordResetClaimed)

            reclaimed_at = now + timedelta(minutes=10, seconds=1)
            second = await store.claim(
                email="expired-pending@example.com",
                code_hash="b" * 64,
                expires_at=reclaimed_at + timedelta(minutes=10),
                claimed_at=reclaimed_at,
                cooldown_seconds=60,
            )

            assert isinstance(second, PasswordResetClaimed)
            assert await store.activate(
                challenge_id=first.challenge.id,
                delivery_id=first.challenge.delivery_id,
                activated_at=reclaimed_at,
            ) is None
            assert await store.activate(
                challenge_id=second.challenge.id,
                delivery_id=second.challenge.delivery_id,
                activated_at=reclaimed_at,
            ) is not None
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_concurrent_password_reset_completion_has_one_winner(tmp_path: Path) -> None:
    async def run() -> None:
        factory, engine = await _database(tmp_path / "complete.db")
        try:
            await _seed_user(factory, email="complete@example.com")
            store = SqlAlchemyPasswordResetStore(factory)
            now = datetime.now(UTC)
            await _claim_and_activate(
                store,
                email="complete@example.com",
                code_hash="c" * 64,
                now=now,
            )
            gate = asyncio.Event()

            async def complete(password_hash: str):
                await gate.wait()
                return await store.complete(
                    email="complete@example.com",
                    code_hash="c" * 64,
                    password_hash_factory=lambda: password_hash,
                    completed_at=now + timedelta(seconds=1),
                    max_attempts=5,
                )

            tasks = [
                asyncio.create_task(complete("winner-one")),
                asyncio.create_task(complete("winner-two")),
            ]
            gate.set()
            outcomes = await asyncio.gather(*tasks)

            assert sum(isinstance(item, PasswordResetCompleted) for item in outcomes) == 1
            assert sum(isinstance(item, PasswordResetInvalid) for item in outcomes) == 1
            winning_hash = (
                "winner-one"
                if isinstance(outcomes[0], PasswordResetCompleted)
                else "winner-two"
            )
            async with factory() as session:
                stored_hash = await session.scalar(
                    select(AppUser.password_hash).where(AppUser.email == "complete@example.com")
                )
            assert stored_hash == winning_hash
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_password_update_failure_rolls_back_challenge_consumption(tmp_path: Path) -> None:
    async def run() -> None:
        factory, engine = await _database(tmp_path / "rollback.db")
        try:
            await _seed_user(factory, email="rollback@example.com")
            store = SqlAlchemyPasswordResetStore(factory)
            now = datetime.now(UTC)
            await _claim_and_activate(
                store,
                email="rollback@example.com",
                code_hash="d" * 64,
                now=now,
            )

            def fail_user_update(
                _connection: object,
                _cursor: object,
                statement: str,
                _parameters: object,
                _context: object,
                _executemany: bool,
            ) -> None:
                if statement.lstrip().upper().startswith("UPDATE APP_USER"):
                    raise sqlite3.OperationalError("forced user update failure")

            event.listen(engine.sync_engine, "before_cursor_execute", fail_user_update)
            with pytest.raises(sqlite3.OperationalError, match="forced user update failure"):
                await store.complete(
                    email="rollback@example.com",
                    code_hash="d" * 64,
                    password_hash_factory=lambda: "new-password-hash",
                    completed_at=now + timedelta(seconds=1),
                    max_attempts=5,
                )
            event.remove(engine.sync_engine, "before_cursor_execute", fail_user_update)

            assert await store.get_active(email="rollback@example.com") is not None
        finally:
            await engine.dispose()

    asyncio.run(run())
