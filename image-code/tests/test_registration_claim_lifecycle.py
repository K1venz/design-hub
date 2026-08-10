from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from design_hub.infrastructure.db.base import Base
from design_hub.infrastructure.db.models import RegistrationChallengeRow
from design_hub.infrastructure.db.registration_repo import SqlAlchemyRegistrationStore
from design_hub.ports import registration as registration_port


async def _database(
    path: Path | None = None,
) -> tuple[async_sessionmaker[AsyncSession], AsyncEngine]:
    url = "sqlite+aiosqlite:///:memory:"
    connect_args: dict[str, object] = {}
    if path is not None:
        url = f"sqlite+aiosqlite:///{path.as_posix()}"
        connect_args = {"autocommit": False, "timeout": 1.0}
    engine = create_async_engine(url, connect_args=connect_args)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def _claim_initial(
    store: SqlAlchemyRegistrationStore,
    *,
    email: str = "designer@example.com",
    claimed_at: datetime | None = None,
    code_hash: str = "a" * 64,
):
    claimed_at = claimed_at or datetime(2026, 8, 10, 2, 0, tzinfo=UTC)
    return await store.claim_initial(
        email=email,
        name="Pending Designer",
        password_hash="$2b$12$pending-password-hash",
        code_hash=code_hash,
        expires_at=claimed_at + timedelta(minutes=10),
        claimed_at=claimed_at,
        cooldown_seconds=60,
    )


async def _activate(
    store: SqlAlchemyRegistrationStore,
    challenge: object,
    *,
    activated_at: datetime | None = None,
):
    activated_at = activated_at or datetime(2026, 8, 10, 2, 0, 1, tzinfo=UTC)
    return await store.activate(
        challenge_id=challenge.id,
        delivery_id=challenge.delivery_id,
        activated_at=activated_at,
    )


def test_claim_is_not_verifiable_until_expected_delivery_is_activated() -> None:
    async def scenario() -> None:
        sessions, engine = await _database()
        store = SqlAlchemyRegistrationStore(sessions)
        try:
            result = await _claim_initial(store)
            assert isinstance(result, registration_port.RegistrationClaimed)
            pending = result.challenge
            assert pending.delivery_state is registration_port.RegistrationDeliveryState.PENDING
            assert await store.get_active(email=pending.email, challenge_id=pending.id) is None

            assert (
                await store.activate(
                    challenge_id=pending.id,
                    delivery_id="wrong-delivery-id",
                    activated_at=datetime(2026, 8, 10, 2, 0, 1, tzinfo=UTC),
                )
                is None
            )
            active = await _activate(store, pending)

            assert active is not None
            assert active.delivery_state is registration_port.RegistrationDeliveryState.ACTIVE
            assert await store.get_active(email=active.email, challenge_id=active.id) == active
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_new_initial_claim_rotates_identity_and_old_browser_cannot_verify() -> None:
    async def scenario() -> None:
        sessions, engine = await _database()
        store = SqlAlchemyRegistrationStore(sessions)
        first_at = datetime(2026, 8, 10, 2, 0, tzinfo=UTC)
        second_at = first_at + timedelta(seconds=61)
        try:
            first_result = await _claim_initial(store, claimed_at=first_at)
            assert isinstance(first_result, registration_port.RegistrationClaimed)
            first = first_result.challenge
            assert await _activate(store, first) is not None

            second_result = await _claim_initial(
                store,
                claimed_at=second_at,
                code_hash="b" * 64,
            )
            assert isinstance(second_result, registration_port.RegistrationClaimed)
            second = second_result.challenge

            assert second.id != first.id
            assert second.delivery_id != first.delivery_id
            assert await store.get_active(email=first.email, challenge_id=first.id) is None
            assert (
                await store.complete(
                    expected=first,
                    completed_at=second_at + timedelta(seconds=1),
                )
                == registration_port.RegistrationInvalid()
            )
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_initial_claim_enforces_cooldown_inside_the_repository() -> None:
    async def scenario() -> None:
        sessions, engine = await _database()
        store = SqlAlchemyRegistrationStore(sessions)
        claimed_at = datetime(2026, 8, 10, 2, 0, tzinfo=UTC)
        try:
            first = await _claim_initial(store, claimed_at=claimed_at)
            second = await _claim_initial(
                store,
                claimed_at=claimed_at + timedelta(seconds=1),
                code_hash="b" * 64,
            )

            assert isinstance(first, registration_port.RegistrationClaimed)
            assert isinstance(second, registration_port.RegistrationCooldown)
            assert second.retry_after_seconds == 59
            async with sessions() as session:
                rows = await session.scalar(
                    select(func.count()).select_from(RegistrationChallengeRow)
                )
                stored = await session.get(
                    RegistrationChallengeRow,
                    first.challenge.id,
                )
            assert rows == 1
            assert stored is not None
            assert stored.code_hash == "a" * 64
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_concurrent_first_issuance_has_exactly_one_claim_winner(tmp_path: Path) -> None:
    async def scenario() -> None:
        sessions, engine = await _database(tmp_path / "initial-claim.db")
        store = SqlAlchemyRegistrationStore(sessions)
        start = asyncio.Barrier(2)
        claimed_at = datetime(2026, 8, 10, 2, 0, tzinfo=UTC)

        async def claim(code_hash: str):
            await start.wait()
            return await _claim_initial(
                store,
                claimed_at=claimed_at,
                code_hash=code_hash,
            )

        try:
            results = await asyncio.gather(claim("a" * 64), claim("b" * 64))

            assert (
                sum(isinstance(result, registration_port.RegistrationClaimed) for result in results)
                == 1
            )
            assert (
                sum(
                    isinstance(
                        result,
                        (
                            registration_port.RegistrationCooldown,
                            registration_port.RegistrationClaimContended,
                        ),
                    )
                    for result in results
                )
                == 1
            )
            async with sessions() as session:
                rows = await session.scalar(
                    select(func.count()).select_from(RegistrationChallengeRow)
                )
            assert rows == 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_concurrent_resend_has_one_winner_and_rotates_public_identity(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        sessions, engine = await _database(tmp_path / "resend-claim.db")
        store = SqlAlchemyRegistrationStore(sessions)
        first_at = datetime(2026, 8, 10, 2, 0, tzinfo=UTC)
        resend_at = first_at + timedelta(seconds=61)
        start = asyncio.Barrier(2)
        try:
            initial = await _claim_initial(store, claimed_at=first_at)
            assert isinstance(initial, registration_port.RegistrationClaimed)
            challenge = initial.challenge
            assert await _activate(store, challenge) is not None

            async def resend(code_hash: str):
                await start.wait()
                return await store.claim_resend(
                    email=challenge.email,
                    challenge_id=challenge.id,
                    code_hash=code_hash,
                    expires_at=resend_at + timedelta(minutes=10),
                    claimed_at=resend_at,
                    cooldown_seconds=60,
                )

            results = await asyncio.gather(resend("b" * 64), resend("c" * 64))

            winners = [
                result
                for result in results
                if isinstance(result, registration_port.RegistrationClaimed)
            ]
            assert len(winners) == 1
            assert winners[0].challenge.id != challenge.id
            assert winners[0].challenge.delivery_id != challenge.delivery_id
            assert (
                sum(
                    isinstance(
                        result,
                        (
                            registration_port.RegistrationCooldown,
                            registration_port.RegistrationClaimContended,
                            registration_port.RegistrationClaimInvalid,
                        ),
                    )
                    for result in results
                )
                == 1
            )
        finally:
            await engine.dispose()

    asyncio.run(scenario())
