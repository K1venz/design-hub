"""UserRepository 的 SQLAlchemy 实现（ISSUE-0015）。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.enums import Role
from design_hub.domain.errors import NotFoundError
from design_hub.infrastructure.db.models import AppUser
from design_hub.ports.user_repository import UserAccount, UserRepository


def _to_account(row: AppUser) -> UserAccount:
    return UserAccount(
        id=row.id,
        email=row.email,
        name=row.name,
        role=Role(row.role),
        created_at=row.created_at,
        password_hash=row.password_hash,
    )


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_by_email(self, email: str) -> UserAccount | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(select(AppUser).where(AppUser.email == email))
            ).scalar_one_or_none()
            return _to_account(row) if row is not None else None

    async def get_by_id(self, user_id: int) -> UserAccount | None:
        async with self._session_factory() as session:
            row = await session.get(AppUser, user_id)
            return _to_account(row) if row is not None else None

    async def add(
        self, *, email: str, password_hash: str, name: str, role: Role
    ) -> UserAccount:
        async with self._session_factory() as session:
            row = AppUser(
                email=email, password_hash=password_hash, name=name, role=role.value
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _to_account(row)

    async def set_role(self, user_id: int, role: Role) -> UserAccount:
        async with self._session_factory() as session:
            row = await session.get(AppUser, user_id)
            if row is None:
                raise NotFoundError(f"user {user_id} not found")
            row.role = role.value
            await session.commit()
            await session.refresh(row)
            return _to_account(row)

    async def list_all(self) -> list[UserAccount]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(select(AppUser).order_by(AppUser.id))
            ).scalars().all()
            return [_to_account(r) for r in rows]

    async def count_by_role(self, role: Role) -> int:
        async with self._session_factory() as session:
            n = (
                await session.execute(
                    select(func.count()).select_from(AppUser).where(AppUser.role == role.value)
                )
            ).scalar_one()
            return int(n)
