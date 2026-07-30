import asyncio
from datetime import UTC, datetime
from decimal import Decimal

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

from design_hub.application.admin.admin_console_service import AdminConsoleService
from design_hub.application.admin.user_admin_service import UserAdminService
from design_hub.domain.admin import ModelCallStatus, ModelModality, ModelOperation
from design_hub.domain.enums import Role
from design_hub.domain.errors import DomainError
from design_hub.domain.models import AuthUser
from design_hub.infrastructure.db.admin_console_repo import (
    SqlAlchemyAdminConsoleRepository,
)
from design_hub.infrastructure.db.base import Base
from design_hub.infrastructure.db.models import (
    AdminAuditLogRow,
    AppUser,
    ListingImageRow,
    ListingJobRow,
    ModelCallRow,
)
from design_hub.infrastructure.db.user_repo import SqlAlchemyUserRepository
from design_hub.interface.api.app import register_error_handlers
from design_hub.interface.api.deps import get_current_user, get_user_admin_service
from design_hub.interface.api.routes import admin_console, users
from design_hub.ports.admin_console import (
    AdminImageFilter,
    DateRange,
    ModelCallFilter,
)
from design_hub.ports.media_url_signer import MediaUrlSigner
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


async def _admin_database() -> tuple[
    async_sessionmaker[AsyncSession],
    AsyncEngine,
]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    at = datetime(2026, 7, 15, 12, tzinfo=UTC)
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
                    "created_at": at,
                },
                {
                    "id": 2,
                    "email": "user@example.com",
                    "password_hash": "hash",
                    "name": "User",
                    "role": Role.DESIGNER.value,
                    "created_at": at,
                },
            ],
        )
        await connection.execute(
            ListingJobRow.__table__.insert(),
            [
                {
                    "id": f"job-{index}",
                    "user_id": "2",
                    "idempotency_key": f"key-{index}",
                    "request_fingerprint": f"fingerprint-{index}",
                    "prompt": f"prompt {index}",
                    "modifiers": {},
                    "ratio": "1:1",
                    "size": "1024x1024",
                    "n": 1,
                    "status": "完成",
                    "total_cost": Decimal("0.05"),
                    "created_at": at,
                    "completed_at": at,
                }
                for index in range(3)
            ],
        )
        await connection.execute(
            ListingImageRow.__table__.insert(),
            [
                {
                    "job_id": f"job-{index}",
                    "image_key": f"image-{index}.png",
                    "seed": index,
                    "cost": Decimal("0.05"),
                    "status": "成功",
                    "moderation_status": "normal",
                    "created_at": at,
                }
                for index in range(3)
            ],
        )
        await connection.execute(
            ModelCallRow.__table__.insert(),
            [
                {
                    "id": "image-call-1",
                    "user_id": "2",
                    "provider": "apinebula",
                    "model": "gpt-image-2",
                    "modality": ModelModality.IMAGE.value,
                    "operation_type": ModelOperation.IMAGE_EDIT.value,
                    "attempt_no": 1,
                    "status": ModelCallStatus.FAILED.value,
                    "started_at": at,
                    "completed_at": at,
                    "input_tokens": None,
                    "output_tokens": None,
                    "total_tokens": None,
                    "platform_cost": None,
                },
                {
                    "id": "image-call-2",
                    "user_id": "2",
                    "provider": "apinebula",
                    "model": "gpt-image-2",
                    "modality": ModelModality.IMAGE.value,
                    "operation_type": ModelOperation.IMAGE_EDIT.value,
                    "attempt_no": 2,
                    "status": ModelCallStatus.SUCCEEDED.value,
                    "started_at": at,
                    "completed_at": at,
                    "input_tokens": None,
                    "output_tokens": None,
                    "total_tokens": None,
                    "platform_cost": Decimal("0.05"),
                },
                {
                    "id": "image-call-3",
                    "user_id": "2",
                    "provider": "apinebula",
                    "model": "gpt-image-2",
                    "modality": ModelModality.IMAGE.value,
                    "operation_type": ModelOperation.IMAGE_GENERATION.value,
                    "attempt_no": 1,
                    "status": ModelCallStatus.UNCERTAIN.value,
                    "started_at": at,
                    "completed_at": at,
                    "input_tokens": None,
                    "output_tokens": None,
                    "total_tokens": None,
                    "platform_cost": None,
                },
                {
                    "id": "chat-call-1",
                    "user_id": "2",
                    "provider": "volcengine",
                    "model": "doubao-chat",
                    "modality": ModelModality.CHAT.value,
                    "operation_type": ModelOperation.CHAT_COMPLETION.value,
                    "attempt_no": 1,
                    "status": ModelCallStatus.SUCCEEDED.value,
                    "input_tokens": 21,
                    "output_tokens": 8,
                    "total_tokens": 29,
                    "started_at": at,
                    "completed_at": at,
                    "platform_cost": None,
                },
                {
                    "id": "stale-chat-call",
                    "user_id": "2",
                    "provider": "volcengine",
                    "model": "doubao-chat",
                    "modality": ModelModality.CHAT.value,
                    "operation_type": ModelOperation.CHAT_COMPLETION.value,
                    "attempt_no": 1,
                    "status": ModelCallStatus.STARTED.value,
                    "started_at": at,
                    "completed_at": None,
                    "input_tokens": None,
                    "output_tokens": None,
                    "total_tokens": None,
                    "platform_cost": None,
                },
            ],
        )
        await connection.execute(
            AdminAuditLogRow.__table__.insert(),
            {
                "id": "audit-1",
                "actor_user_id": 1,
                "action": "user.status.update",
                "target_type": "user",
                "target_id": "2",
                "before": {"enabled": True},
                "after": {"enabled": False},
                "reason": "test",
                "created_at": at,
            },
        )
    return async_sessionmaker(engine, expire_on_commit=False), engine


def test_model_call_summary_counts_actual_attempts_and_retries() -> None:
    async def run() -> None:
        sessions, engine = await _admin_database()
        try:
            repository = SqlAlchemyAdminConsoleRepository(sessions)
            rows = await repository.summarize_model_calls(
                ModelCallFilter(
                    date_range=DateRange(
                        start=datetime(2026, 7, 1, tzinfo=UTC),
                        end=datetime(2026, 8, 1, tzinfo=UTC),
                    )
                )
            )
            image = next(row for row in rows if row.model == "gpt-image-2")
            assert image.calls == 3
            assert image.failed == 1
            assert image.uncertain == 1
            assert image.retries == 1
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_admin_images_use_stable_pagination() -> None:
    async def run() -> None:
        sessions, engine = await _admin_database()
        try:
            repository = SqlAlchemyAdminConsoleRepository(sessions)
            first = await repository.list_images(
                AdminImageFilter(),
                limit=2,
                offset=0,
            )
            second = await repository.list_images(
                AdminImageFilter(),
                limit=2,
                offset=2,
            )
            assert first.total == 3
            assert {item.image_id for item in first.items}.isdisjoint(
                item.image_id for item in second.items
            )
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_non_manager_cannot_read_admin_overview() -> None:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(admin_console.router)
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        user_id="2",
        name="User",
        role=Role.DESIGNER,
        dept=None,
    )

    response = TestClient(app).get("/admin/overview")

    assert response.status_code == 403


class _AdminSigner(MediaUrlSigner):
    def generated_url(self, key: str) -> str:
        return f"https://generated.example/{key}"

    def upload_url(self, key: str) -> str:
        return f"https://uploads.example/{key}"


def test_manager_console_http_contracts_and_stale_call_status() -> None:
    sessions, engine = asyncio.run(_admin_database())
    app = FastAPI()
    register_error_handlers(app)
    app.state.admin_console_service = AdminConsoleService(
        SqlAlchemyAdminConsoleRepository(sessions)
    )
    app.state.media_signer = _AdminSigner()
    app.include_router(admin_console.router)
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        user_id="1",
        name="Manager",
        role=Role.MANAGER,
        dept=None,
    )
    client = TestClient(app)

    overview_response = client.get(
        "/admin/overview"
        "?start=2026-07-01T00:00:00Z"
        "&end=2026-08-01T00:00:00Z"
    )
    users_response = client.get("/admin/users?limit=2")
    images_response = client.get("/admin/images?limit=2")
    calls_response = client.get(
        "/admin/model-calls?status=uncertain"
        "&start=2026-07-01T00:00:00Z"
        "&end=2026-08-01T00:00:00Z"
    )
    audit_response = client.get("/admin/audit-logs")

    assert overview_response.status_code == 200
    assert overview_response.json()["image_calls"] == 3
    assert users_response.status_code == 200
    assert users_response.json()["total"] == 2
    assert images_response.status_code == 200
    assert images_response.json()["items"][0]["url"].startswith(
        "https://generated.example/"
    )
    assert calls_response.status_code == 200
    assert {item["call_id"] for item in calls_response.json()["items"]} == {
        "image-call-3",
        "stale-chat-call",
    }
    assert audit_response.status_code == 200
    assert audit_response.json()["items"][0]["actor_email"] == (
        "manager@example.com"
    )

    invalid_range = client.get(
        "/admin/overview"
        "?start=2026-08-01T00:00:00Z"
        "&end=2026-07-01T00:00:00Z"
    )
    assert invalid_range.status_code == 400

    asyncio.run(engine.dispose())


def test_image_moderation_is_audited_reversible_and_rejects_noop() -> None:
    sessions, engine = asyncio.run(_admin_database())
    app = FastAPI()
    register_error_handlers(app)
    app.state.admin_console_service = AdminConsoleService(
        SqlAlchemyAdminConsoleRepository(sessions)
    )
    app.state.media_signer = _AdminSigner()
    app.include_router(admin_console.router)
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        user_id="1",
        name="Manager",
        role=Role.MANAGER,
        dept=None,
    )
    client = TestClient(app)
    payload = {
        "status": "blocked",
        "reason": "illegal",
        "note": "manual review",
    }

    blocked = client.put("/admin/images/1/moderation", json=payload)
    repeated = client.put("/admin/images/1/moderation", json=payload)
    restored = client.put(
        "/admin/images/1/moderation",
        json={"status": "normal"},
    )

    assert blocked.status_code == 200
    assert blocked.json()["moderation_status"] == "blocked"
    assert blocked.json()["url"].endswith("/image-0.png")
    assert repeated.status_code == 409
    assert restored.status_code == 200
    assert restored.json()["moderation_status"] == "normal"
    assert restored.json()["moderation_reason"] is None
    assert restored.json()["moderation_note"] is None

    async def verify() -> None:
        async with sessions() as session:
            audits = (
                await session.execute(
                    select(AdminAuditLogRow).where(
                        AdminAuditLogRow.action
                        == "image.moderation.update"
                    )
                )
            ).scalars().all()
        assert len(audits) == 2
        assert audits[0].before == {"status": "normal"}
        assert audits[0].after == {
            "status": "blocked",
            "reason": "illegal",
            "note": "manual review",
        }
        assert audits[1].after == {"status": "normal"}

    asyncio.run(verify())
    asyncio.run(engine.dispose())
