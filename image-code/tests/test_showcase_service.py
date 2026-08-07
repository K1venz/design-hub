import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from io import BytesIO

import pytest
from PIL import Image

from design_hub.application.showcase.service import ShowcaseService
from design_hub.domain.errors import DomainError
from design_hub.ports.image_store import ImageStore, StoredImage
from design_hub.ports.showcase import (
    ShowcaseCandidate,
    ShowcasePublication,
    ShowcaseRepository,
)


def _jpeg() -> bytes:
    output = BytesIO()
    Image.new("RGB", (2400, 1200), (50, 100, 150)).save(output, format="JPEG")
    return output.getvalue()


class _ImageStore(ImageStore):
    def __init__(self, source: bytes) -> None:
        self.source = source
        self.loaded: list[str] = []
        self.saved: list[tuple[bytes, str]] = []

    async def load(self, image_key: str) -> bytes:
        self.loaded.append(image_key)
        return self.source

    async def save(self, data: bytes, *, suffix: str = ".png") -> StoredImage:
        self.saved.append((data, suffix))
        return StoredImage(key="preview.webp", url="https://preview.example/preview.webp")


class _Repository(ShowcaseRepository):
    def __init__(self, candidate: ShowcaseCandidate | None) -> None:
        self.candidate = candidate
        self.updates: list[dict[str, object]] = []

    async def get_candidate(self, image_id: int) -> ShowcaseCandidate | None:
        if self.candidate is None or self.candidate.image_id != image_id:
            return None
        return self.candidate

    async def set_publication(
        self,
        *,
        actor_id: int,
        image_id: int,
        is_public: bool,
        download_allowed: bool,
        preview_key: str | None,
        preview_width: int | None,
        preview_height: int | None,
    ) -> ShowcasePublication:
        self.updates.append(
            {
                "actor_id": actor_id,
                "image_id": image_id,
                "is_public": is_public,
                "download_allowed": download_allowed,
                "preview_key": preview_key,
                "preview_width": preview_width,
                "preview_height": preview_height,
            }
        )
        return ShowcasePublication(
            image_id=image_id,
            is_public=is_public,
            download_allowed=download_allowed,
            preview_width=preview_width,
            preview_height=preview_height,
            showcased_at=datetime.now(UTC) if is_public else None,
            showcased_by=actor_id if is_public else None,
        )

    async def list_public(self):  # type: ignore[no-untyped-def]
        raise AssertionError("not used")

    async def get_download_key(self, image_id: int) -> str | None:
        raise AssertionError("not used")


def _candidate(**changes: object) -> ShowcaseCandidate:
    base = ShowcaseCandidate(
        image_id=7,
        image_key="original.png",
        image_type="场景",
        status="成功",
        moderation_status="normal",
        prompt="暖色早餐桌，突出花生礼盒",
        category="FOOD",
        ratio="1:1",
        modifiers={"platform": "淘宝天猫1688"},
        is_public=False,
        download_allowed=False,
        preview_key=None,
        preview_width=None,
        preview_height=None,
    )
    return replace(base, **changes)


def test_publish_creates_preview_and_persists_dimensions() -> None:
    async def run() -> None:
        repository = _Repository(_candidate())
        store = _ImageStore(_jpeg())
        service = ShowcaseService(repository=repository, images=store)

        result = await service.set_publication(
            actor_id=1,
            image_id=7,
            is_public=True,
            download_allowed=False,
        )

        assert result.is_public is True
        assert store.loaded == ["original.png"]
        assert len(store.saved) == 1
        assert store.saved[0][1] == ".webp"
        assert repository.updates == [
            {
                "actor_id": 1,
                "image_id": 7,
                "is_public": True,
                "download_allowed": False,
                "preview_key": "preview.webp",
                "preview_width": 1200,
                "preview_height": 600,
            }
        ]

    asyncio.run(run())


def test_download_policy_update_reuses_existing_preview() -> None:
    async def run() -> None:
        repository = _Repository(
            _candidate(
                is_public=True,
                preview_key="existing.webp",
                preview_width=900,
                preview_height=600,
            )
        )
        store = _ImageStore(_jpeg())
        service = ShowcaseService(repository=repository, images=store)

        result = await service.set_publication(
            actor_id=1,
            image_id=7,
            is_public=True,
            download_allowed=True,
        )

        assert result.download_allowed is True
        assert store.loaded == []
        assert store.saved == []
        assert repository.updates[0]["preview_key"] == "existing.webp"

    asyncio.run(run())


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"status": "失败"}, "只有生成成功的图片可以公开展示"),
        ({"moderation_status": "blocked"}, "已屏蔽图片不能公开展示"),
        ({"prompt": "  "}, "缺少用户原始提示词，不能公开展示"),
        ({"image_type": None}, "缺少可复用图型，不能公开展示"),
        ({"category": None}, "缺少商品品类，不能公开展示"),
    ],
)
def test_publish_rejects_ineligible_image(
    changes: dict[str, object],
    message: str,
) -> None:
    async def run() -> None:
        repository = _Repository(_candidate(**changes))
        store = _ImageStore(_jpeg())
        service = ShowcaseService(repository=repository, images=store)

        with pytest.raises(ValueError, match=f"^{message}$"):
            await service.set_publication(
                actor_id=1,
                image_id=7,
                is_public=True,
                download_allowed=False,
            )

        assert repository.updates == []
        assert store.loaded == []

    asyncio.run(run())


def test_private_image_cannot_allow_original_download() -> None:
    async def run() -> None:
        service = ShowcaseService(
            repository=_Repository(_candidate()),
            images=_ImageStore(_jpeg()),
        )

        with pytest.raises(ValueError, match="^未公开图片不能允许下载$"):
            await service.set_publication(
                actor_id=1,
                image_id=7,
                is_public=False,
                download_allowed=True,
            )

    asyncio.run(run())


def test_unchanged_publication_fails_fast() -> None:
    async def run() -> None:
        service = ShowcaseService(
            repository=_Repository(_candidate()),
            images=_ImageStore(_jpeg()),
        )

        with pytest.raises(DomainError, match="^公开展示状态没有变化$"):
            await service.set_publication(
                actor_id=1,
                image_id=7,
                is_public=False,
                download_allowed=False,
            )

    asyncio.run(run())


def test_preview_failure_does_not_persist_publication() -> None:
    async def run() -> None:
        repository = _Repository(_candidate())
        service = ShowcaseService(
            repository=repository,
            images=_ImageStore(b"broken"),
        )

        with pytest.raises(ValueError, match="^公开预览图无法解码$"):
            await service.set_publication(
                actor_id=1,
                image_id=7,
                is_public=True,
                download_allowed=False,
            )

        assert repository.updates == []

    asyncio.run(run())
