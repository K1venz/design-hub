"""SQLAlchemy user repository."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.admin import AdminAction
from design_hub.domain.enums import Role
from design_hub.domain.errors import DomainError, NotFoundError
from design_hub.infrastructure.db.models import AdminAuditLogRow, AppUser
from design_hub.ports.user_repository import UserAccount, UserRepository


def _to_account(row: AppUser) -> UserAccount:
    return UserAccount(
        id=row.id,
        email=row.email,
        name=row.name,
        role=Role(row.role),
        created_at=row.created_at,
        password_hash=row.password_hash,
        enabled=row.enabled,
        disabled_at=row.disabled_at,
        disabled_by=row.disabled_by,
        disabled_reason=row.disabled_reason,
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

    async def set_role_with_audit(
        self,
        *,
        actor_id: int,
        user_id: int,
        role: Role,
    ) -> UserAccount:
        async with self._session_factory() as session:
            async with session.begin():
                row = await self._locked_user(session, user_id)
                if (
                    row.role == Role.MANAGER.value
                    and row.enabled
                    and role is Role.DESIGNER
                    and await self._enabled_manager_count(session) <= 1
                ):
                    raise DomainError("不能降级最后一个管理者")
                before = {"role": row.role}
                row.role = role.value
                session.add(
                    AdminAuditLogRow(
                        id=uuid4().hex,
                        actor_user_id=actor_id,
                        action=AdminAction.USER_ROLE_UPDATE.value,
                        target_type="user",
                        target_id=str(user_id),
                        before=before,
                        after={"role": row.role},
                        reason=None,
                    )
                )
            return _to_account(row)

    async def set_status_with_audit(
        self,
        *,
        actor_id: int,
        user_id: int,
        enabled: bool,
        reason: str,
    ) -> UserAccount:
        async with self._session_factory() as session:
            async with session.begin():
                row = await self._locked_user(session, user_id)
                if actor_id == user_id and not enabled:
                    raise DomainError("不能停用自己")
                if (
                    row.role == Role.MANAGER.value
                    and row.enabled
                    and not enabled
                    and await self._enabled_manager_count(session) <= 1
                ):
                    raise DomainError("不能停用最后一个管理者")

                before = {"enabled": row.enabled}
                row.enabled = enabled
                if enabled:
                    row.disabled_at = None
                    row.disabled_by = None
                    row.disabled_reason = None
                else:
                    row.disabled_at = datetime.now(UTC)
                    row.disabled_by = actor_id
                    row.disabled_reason = reason
                session.add(
                    AdminAuditLogRow(
                        id=uuid4().hex,
                        actor_user_id=actor_id,
                        action=AdminAction.USER_STATUS_UPDATE.value,
                        target_type="user",
                        target_id=str(user_id),
                        before=before,
                        after={"enabled": row.enabled},
                        reason=reason or None,
                    )
                )
            return _to_account(row)

    async def list_all(self) -> list[UserAccount]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(select(AppUser).order_by(AppUser.id))
            ).scalars().all()
            return [_to_account(r) for r in rows]

    @staticmethod
    async def _locked_user(session: AsyncSession, user_id: int) -> AppUser:
        row = (
            await session.execute(
                select(AppUser)
                .where(AppUser.id == user_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError(f"user {user_id} not found")
        return row

    @staticmethod
    async def _enabled_manager_count(session: AsyncSession) -> int:
        ids = (
            await session.execute(
                select(AppUser.id)
                .where(
                    AppUser.role == Role.MANAGER.value,
                    AppUser.enabled.is_(True),
                )
                .order_by(AppUser.id)
                .with_for_update()
            )
        ).scalars().all()
        return len(ids)
