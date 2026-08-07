import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from design_hub.application.showcase.service import ShowcaseService
from design_hub.infrastructure.db.base import Base
from design_hub.infrastructure.db.models import AppUser, ListingImageRow, ListingJobRow
from design_hub.infrastructure.db.showcase_repo import SqlAlchemyShowcaseRepository
from design_hub.interface.api.app import register_error_handlers
from design_hub.interface.api.routes import showcase
from design_hub.ports.image_store import ImageStore, StoredImage
from design_hub.ports.media_url_signer import MediaUrlSigner


class _UnusedImageStore(ImageStore):
    async def load(self, image_key: str) -> bytes:
        raise AssertionError("public reads must not load image bytes")

    async def save(self, data: bytes, *, suffix: str = ".png") -> StoredImage:
        raise AssertionError("public reads must not save image bytes")


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
            {
                "id": 1,
                "email": "user@example.com",
                "password_hash": "hash",
                "name": "User",
                "role": "设计师",
                "created_at": at,
            },
        )
        await connection.execute(
            ListingJobRow.__table__.insert(),
            [
                {
                    "id": f"job-{index}",
                    "user_id": "1",
                    "idempotency_key": f"key-{index}",
                    "request_fingerprint": f"fingerprint-{index}",
                    "prompt": f"用户原始提示词 {index}",
                    "modifiers": {
                        "platform": "淘宝天猫1688",
                        "region": "中国",
                        "language": "中文",
                    },
                    "category": None if index == 5 else "FOOD",
                    "ratio": "1:1",
                    "size": "1024x1024",
                    "n": 2 if index == 1 else 1,
                    "status": "完成",
                    "total_cost": Decimal("0.05"),
                    "created_at": at,
                    "completed_at": at,
                }
                for index in range(1, 6)
            ],
        )
        for image in [
                {
                    "id": 1,
                    "job_id": "job-1",
                    "image_key": "original-1.png",
                    "image_type": "场景",
                    "seed": 1,
                    "cost": Decimal("0.05"),
                    "status": "成功",
                    "moderation_status": "normal",
                    "is_public_showcase": True,
                    "showcase_download_allowed": True,
                    "showcase_preview_key": "preview-1.webp",
                    "showcase_preview_width": 1200,
                    "showcase_preview_height": 600,
                    "showcased_at": at + timedelta(minutes=2),
                    "showcased_by": 9,
                    "created_at": at,
                },
                {
                    "id": 2,
                    "job_id": "job-1",
                    "image_key": "original-2.png",
                    "image_type": "白底",
                    "seed": 2,
                    "cost": Decimal("0.05"),
                    "status": "成功",
                    "moderation_status": "normal",
                    "is_public_showcase": False,
                    "created_at": at,
                },
                {
                    "id": 3,
                    "job_id": "job-2",
                    "image_key": "blocked-original.png",
                    "image_type": "卖点",
                    "seed": 3,
                    "cost": Decimal("0.05"),
                    "status": "成功",
                    "moderation_status": "blocked",
                    "is_public_showcase": True,
                    "showcase_download_allowed": True,
                    "showcase_preview_key": "blocked-preview.webp",
                    "showcase_preview_width": 600,
                    "showcase_preview_height": 1200,
                    "showcased_at": at + timedelta(minutes=3),
                    "showcased_by": 9,
                    "created_at": at,
                },
                {
                    "id": 4,
                    "job_id": "job-3",
                    "image_key": "failed-original.png",
                    "image_type": "场景",
                    "seed": 4,
                    "cost": Decimal("0.05"),
                    "status": "失败",
                    "moderation_status": "normal",
                    "is_public_showcase": True,
                    "showcase_download_allowed": True,
                    "showcase_preview_key": "failed-preview.webp",
                    "showcase_preview_width": 1200,
                    "showcase_preview_height": 1200,
                    "showcased_at": at + timedelta(minutes=4),
                    "showcased_by": 9,
                    "created_at": at,
                },
                {
                    "id": 5,
                    "job_id": "job-4",
                    "image_key": "missing-preview-original.png",
                    "image_type": "场景",
                    "seed": 5,
                    "cost": Decimal("0.05"),
                    "status": "成功",
                    "moderation_status": "normal",
                    "is_public_showcase": True,
                    "showcase_download_allowed": False,
                    "showcased_at": at + timedelta(minutes=5),
                    "showcased_by": 9,
                    "created_at": at,
                },
                {
                    "id": 6,
                    "job_id": "job-5",
                    "image_key": "single-original.png",
                    "image_type": None,
                    "seed": 6,
                    "cost": Decimal("0.05"),
                    "status": "成功",
                    "moderation_status": "normal",
                    "is_public_showcase": True,
                    "showcase_download_allowed": False,
                    "showcase_preview_key": "single-preview.webp",
                    "showcase_preview_width": 720,
                    "showcase_preview_height": 1280,
                    "showcased_at": at + timedelta(minutes=6),
                    "showcased_by": 9,
                    "created_at": at,
                },
        ]:
            await connection.execute(ListingImageRow.__table__.insert(), image)
    return async_sessionmaker(engine, expire_on_commit=False), engine


def test_public_showcase_uses_preview_and_original_prompt_only() -> None:
    sessions, engine = asyncio.run(_database())
    app = FastAPI()
    register_error_handlers(app)
    app.state.showcase_service = ShowcaseService(
        SqlAlchemyShowcaseRepository(sessions),
        _UnusedImageStore(),
    )
    app.state.media_signer = _Signer()
    app.include_router(showcase.router)
    client = TestClient(app)

    response = client.get("/showcase")

    assert response.status_code == 200
    assert response.json() == [
        {
            "image_id": 6,
            "url": "https://generated.example/single-preview.webp",
            "image_type": None,
            "caption": "单图",
            "prompt": "用户原始提示词 5",
            "download_allowed": False,
            "width": 720,
            "height": 1280,
            "recipe": None,
        },
        {
            "image_id": 1,
            "url": "https://generated.example/preview-1.webp",
            "image_type": "场景",
            "caption": "食品 · 场景",
            "prompt": "用户原始提示词 1",
            "download_allowed": True,
            "width": 1200,
            "height": 600,
                "recipe": {
                    "category": "FOOD",
                "ratio": "1:1",
                "plan": {"白底": 1, "场景": 1},
                "styling": "用户原始提示词 1",
                "modifiers": {
                    "platform": "淘宝天猫1688",
                    "region": "中国",
                    "language": "中文",
                },
            },
        }
    ]
    serialized = response.text
    assert "original-1.png" not in serialized
    assert "user@example.com" not in serialized
    assert "moderation" not in serialized
    assert "final_prompt" not in serialized

    asyncio.run(engine.dispose())


def test_original_download_requires_current_public_permission() -> None:
    sessions, engine = asyncio.run(_database())
    app = FastAPI()
    register_error_handlers(app)
    app.state.showcase_service = ShowcaseService(
        SqlAlchemyShowcaseRepository(sessions),
        _UnusedImageStore(),
    )
    app.state.media_signer = _Signer()
    app.include_router(showcase.router)
    client = TestClient(app)

    allowed = client.get("/showcase/1/download")
    private = client.get("/showcase/2/download")
    blocked = client.get("/showcase/3/download")
    failed = client.get("/showcase/4/download")

    assert allowed.status_code == 200
    assert allowed.json() == {
        "url": "https://generated.example/original-1.png"
    }
    assert private.status_code == 404
    assert blocked.status_code == 404
    assert failed.status_code == 404

    asyncio.run(engine.dispose())
