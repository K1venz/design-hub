import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from design_hub.application.admin.user_admin_service import UserAdminService
from design_hub.domain.enums import Role
from design_hub.domain.errors import DomainError
from design_hub.domain.models import AuthUser
from design_hub.infrastructure.db.base import Base
from design_hub.infrastructure.db.models import AdminAuditLogRow, AppUser
from design_hub.infrastructure.db.user_repo import SqlAlchemyUserRepository
from design_hub.interface.api.app import register_error_handlers
from design_hub.interface.api.deps import get_current_user, get_user_admin_service
from design_hub.interface.api.routes import users
from design_hub.ports.user_repository import UserAccount


class _StatusService:
    def __init__(self) -> None:
        self.received: tuple[int, int, bool, str] | None = None

    async def set_status(
        self,
        *,
        actor_id: int,
        user_id: int,
        enabled: bool,
        reason: str,
    ) -> UserAccount:
        self.received = (actor_id, user_id, enabled, reason)
        return UserAccount(
            id=user_id,
            email="user@example.com",
            name="User",
            role=Role.DESIGNER,
            created_at=datetime.now(UTC),
            password_hash="hash",
            enabled=enabled,
            disabled_reason=reason,
        )


async def _users_database() -> tuple[
    async_sessionmaker[AsyncSession],
    AsyncEngine,
]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            AppUser.__table__.insert(),
            [
                {
                    "id": 1,
                    "email": "manager@example.com",
                    "password_hash": "hash",
                    "name": "Manager",
                    "role": Role.MANAGER.value,
                },
                {
                    "id": 2,
                    "email": "user@example.com",
                    "password_hash": "hash",
                    "name": "User",
                    "role": Role.DESIGNER.value,
                },
            ],
        )
    return async_sessionmaker(engine, expire_on_commit=False), engine


def test_manager_cannot_disable_self() -> None:
    async def run() -> None:
        sessions, engine = await _users_database()
        try:
            service = UserAdminService(SqlAlchemyUserRepository(sessions))

            with pytest.raises(DomainError, match="不能停用自己"):
                await service.set_status(
                    actor_id=1,
                    user_id=1,
                    enabled=False,
                    reason="test",
                )
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_last_enabled_manager_cannot_be_disabled_or_demoted() -> None:
    async def run() -> None:
        sessions, engine = await _users_database()
        try:
            service = UserAdminService(SqlAlchemyUserRepository(sessions))

            with pytest.raises(DomainError, match="最后一个管理者"):
                await service.set_status(
                    actor_id=2,
                    user_id=1,
                    enabled=False,
                    reason="test",
                )
            with pytest.raises(DomainError, match="最后一个管理者"):
                await service.set_role(
                    actor_id=2,
                    user_id=1,
                    role=Role.DESIGNER,
                )
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_user_status_change_and_audit_commit_together() -> None:
    async def run() -> None:
        sessions, engine = await _users_database()
        try:
            service = UserAdminService(SqlAlchemyUserRepository(sessions))

            account = await service.set_status(
                actor_id=1,
                user_id=2,
                enabled=False,
                reason="  合规处置  ",
            )

            assert account.enabled is False
            assert account.disabled_by == 1
            assert account.disabled_reason == "合规处置"
            async with sessions() as session:
                row = await session.get(AppUser, 2)
                audit = (
                    await session.execute(select(AdminAuditLogRow))
                ).scalar_one()
            assert row is not None and row.enabled is False
            assert audit.action == "user.status.update"
            assert audit.before == {"enabled": True}
            assert audit.after == {"enabled": False}
            assert audit.reason == "合规处置"
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_restoring_user_clears_disable_metadata() -> None:
    async def run() -> None:
        sessions, engine = await _users_database()
        try:
            service = UserAdminService(SqlAlchemyUserRepository(sessions))
            await service.set_status(
                actor_id=1,
                user_id=2,
                enabled=False,
                reason="合规处置",
            )

            account = await service.set_status(
                actor_id=1,
                user_id=2,
                enabled=True,
                reason="",
            )

            assert account.enabled is True
            assert account.disabled_at is None
            assert account.disabled_by is None
            assert account.disabled_reason is None
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_user_status_route_uses_current_manager_as_actor() -> None:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(users.router)
    service = _StatusService()
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        user_id="9",
        name="Manager",
        role=Role.MANAGER,
        dept=None,
    )
    app.dependency_overrides[get_user_admin_service] = lambda: service
    client = TestClient(app)

    response = client.put(
        "/admin/users/2/status",
        json={"enabled": False, "reason": "合规处置"},
    )

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert service.received == (9, 2, False, "合规处置")
