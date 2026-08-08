"""SQLAlchemy store for password-reset challenges."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.infrastructure.db.models import PasswordResetChallengeRow
from design_hub.ports.password_reset import PasswordResetChallenge, PasswordResetStore


def _to_challenge(row: PasswordResetChallengeRow) -> PasswordResetChallenge:
    return PasswordResetChallenge(
        id=row.id,
        email=row.email,
        code_hash=row.code_hash,
        expires_at=row.expires_at,
        attempt_count=row.attempt_count,
        created_at=row.created_at,
        consumed_at=row.consumed_at,
    )


class SqlAlchemyPasswordResetStore(PasswordResetStore):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_active(self, email: str) -> PasswordResetChallenge | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(PasswordResetChallengeRow)
                    .where(
                        PasswordResetChallengeRow.email == email,
                        PasswordResetChallengeRow.consumed_at.is_(None),
                    )
                    .order_by(PasswordResetChallengeRow.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            return _to_challenge(row) if row is not None else None

    async def replace_active(
        self,
        *,
        email: str,
        code_hash: str,
        expires_at: datetime,
    ) -> PasswordResetChallenge:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(PasswordResetChallengeRow)
                    .where(
                        PasswordResetChallengeRow.email == email,
                        PasswordResetChallengeRow.consumed_at.is_(None),
                    )
                    .values(consumed_at=now)
                )
                row = PasswordResetChallengeRow(
                    id=uuid4().hex,
                    email=email,
                    code_hash=code_hash,
                    expires_at=expires_at,
                    attempt_count=0,
                    consumed_at=None,
                )
                session.add(row)
                await session.flush()
                await session.refresh(row)
                return _to_challenge(row)

    async def record_failed_attempt(self, challenge_id: str) -> PasswordResetChallenge | None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(PasswordResetChallengeRow, challenge_id)
                if row is None or row.consumed_at is not None:
                    return None
                row.attempt_count += 1
            return _to_challenge(row)

    async def consume(self, challenge_id: str) -> None:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(PasswordResetChallengeRow)
                    .where(
                        PasswordResetChallengeRow.id == challenge_id,
                        PasswordResetChallengeRow.consumed_at.is_(None),
                    )
                    .values(consumed_at=now)
                )
