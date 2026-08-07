import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from design_hub.application.admin.admin_console_service import AdminConsoleService
from design_hub.application.showcase.service import ShowcaseService
from design_hub.domain.enums import Role
from design_hub.domain.models import AuthUser
from design_hub.infrastructure.db.admin_console_repo import SqlAlchemyAdminConsoleRepository
from design_hub.infrastructure.db.base import Base
from design_hub.infrastructure.db.models import (
    AdminAuditLogRow,
    AppUser,
    ListingImageRow,
    ListingJobRow,
)
from design_hub.infrastructure.db.showcase_repo import SqlAlchemyShowcaseRepository
from design_hub.interface.api.app import register_error_handlers
from design_hub.interface.api.deps import get_current_user
from design_hub.interface.api.routes import admin_console
from design_hub.ports.image_store import ImageStore, StoredImage
from design_hub.ports.media_url_signer import MediaUrlSigner


class _ImageStore(ImageStore):
    async def load(self, image_key: str) -> bytes:
        output = BytesIO()
        Image.new("RGB", (1600, 800), (30, 60, 90)).save(output, format="PNG")
        return output.getvalue()

    async def save(self, data: bytes, *, suffix: str = ".png") -> StoredImage:
        return StoredImage(key="public-preview.webp", url="unused")


class _Signer(MediaUrlSigner):
    def generated_url(self, key: str) -> str:
        return f"https://generated.example/{key}"

    def upload_url(self, key: str) -> str:
        return f"https://uploads.example/{key}"


async def _database() -> tuple[async_sessionmaker[AsyncSession], object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    at = datetime(2026, 8, 7, 10, tzinfo=UTC)
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
            {
                "id": "job-1",
                "user_id": "2",
                "idempotency_key": "key-1",
                "request_fingerprint": "fingerprint-1",
                "prompt": "用户输入的暖色早餐桌提示词",
                "modifiers": {"platform": "淘宝天猫1688"},
                "category": "FOOD",
                "ratio": "2:1",
                "size": "1600x800",
                "n": 1,
                "status": "完成",
                "total_cost": Decimal("0.05"),
                "created_at": at,
                "completed_at": at,
            },
        )
        await connection.execute(
            ListingImageRow.__table__.insert(),
            {
                "id": 1,
                "job_id": "job-1",
                "image_key": "original.png",
                "image_type": "场景",
                "seed": 1,
                "cost": Decimal("0.05"),
                "status": "成功",
                "moderation_status": "normal",
                "created_at": at,
            },
        )
    return async_sessionmaker(engine, expire_on_commit=False), engine


def test_manager_publication_is_filterable_audited_and_cleared_by_blocking() -> None:
    sessions, engine = asyncio.run(_database())
    repository = SqlAlchemyShowcaseRepository(sessions)
    app = FastAPI()
    register_error_handlers(app)
    app.state.showcase_service = ShowcaseService(repository, _ImageStore())
    app.state.admin_console_service = AdminConsoleService(
        SqlAlchemyAdminConsoleRepository(sessions)
    )
    app.state.media_signer = _Signer()
    app.include_router(admin_console.router)
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        user_id="1",
        name="Manager",
        role=Role.MANAGER,
        dept=None,
    )
    client = TestClient(app)

    published = client.put(
        "/admin/images/1/showcase",
        json={"is_public": True, "download_allowed": True},
    )
    repeated = client.put(
        "/admin/images/1/showcase",
        json={"is_public": True, "download_allowed": True},
    )
    public_images = client.get("/admin/images?showcase_status=public")
    blocked = client.put(
        "/admin/images/1/moderation",
        json={"status": "blocked", "reason": "other"},
    )

    assert published.status_code == 200
    assert published.json() == {
        "image_id": 1,
        "is_public": True,
        "download_allowed": True,
        "preview_width": 1200,
        "preview_height": 600,
        "showcased_at": published.json()["showcased_at"],
        "showcased_by": 1,
    }
    assert repeated.status_code == 409
    assert public_images.status_code == 200
    assert public_images.json()["total"] == 1
    item = public_images.json()["items"][0]
    assert item["prompt"] == "用户输入的暖色早餐桌提示词"
    assert item["is_public_showcase"] is True
    assert item["showcase_download_allowed"] is True
    assert item["showcase_preview_width"] == 1200
    assert item["showcase_preview_height"] == 600
    assert blocked.status_code == 200

    async def verify() -> None:
        async with sessions() as session:
            image = await session.get(ListingImageRow, 1)
            assert image is not None
            assert image.is_public_showcase is False
            assert image.showcase_download_allowed is False
            assert image.showcased_at is None
            assert image.showcased_by is None
            actions = (
                await session.execute(
                    select(AdminAuditLogRow.action).order_by(AdminAuditLogRow.created_at)
                )
            ).scalars().all()
        assert "image.showcase.update" in actions
        assert "image.moderation.update" in actions

    asyncio.run(verify())
    asyncio.run(engine.dispose())
