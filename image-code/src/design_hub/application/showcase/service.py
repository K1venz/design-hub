import asyncio
from dataclasses import dataclass

from design_hub.application.showcase.preview import render_showcase_preview
from design_hub.domain.errors import DomainError, NotFoundError
from design_hub.ports.image_store import ImageStore
from design_hub.ports.showcase import (
    PublicShowcaseItem,
    ShowcaseCandidate,
    ShowcasePublication,
    ShowcaseRepository,
)


@dataclass(frozen=True)
class ShowcaseService:
    repository: ShowcaseRepository
    images: ImageStore

    async def set_publication(
        self,
        *,
        actor_id: int,
        image_id: int,
        is_public: bool,
        download_allowed: bool,
    ) -> ShowcasePublication:
        if actor_id < 1:
            raise ValueError("actor_id 必须为正整数")
        if image_id < 1:
            raise ValueError("image_id 必须为正整数")
        if not is_public and download_allowed:
            raise ValueError("未公开图片不能允许下载")

        candidate = await self.repository.get_candidate(image_id)
        if candidate is None:
            raise NotFoundError("图片不存在")
        if (
            candidate.is_public == is_public
            and candidate.download_allowed == download_allowed
        ):
            raise DomainError("公开展示状态没有变化")

        preview_key = candidate.preview_key
        preview_width = candidate.preview_width
        preview_height = candidate.preview_height
        if is_public:
            self._validate_public_candidate(candidate)
            if not self._has_complete_preview(candidate):
                source = await self.images.load(candidate.image_key)
                preview = await asyncio.to_thread(render_showcase_preview, source)
                stored = await self.images.save(preview.data, suffix=".webp")
                preview_key = stored.key
                preview_width = preview.width
                preview_height = preview.height

        return await self.repository.set_publication(
            actor_id=actor_id,
            image_id=image_id,
            is_public=is_public,
            download_allowed=download_allowed,
            preview_key=preview_key,
            preview_width=preview_width,
            preview_height=preview_height,
        )

    async def list_public(self) -> tuple[PublicShowcaseItem, ...]:
        return await self.repository.list_public()

    async def authorize_download(self, image_id: int) -> str:
        if image_id < 1:
            raise NotFoundError("图片不存在")
        key = await self.repository.get_download_key(image_id)
        if key is None:
            raise NotFoundError("图片不存在")
        return key

    @staticmethod
    def _validate_public_candidate(candidate: ShowcaseCandidate) -> None:
        if candidate.status != "成功":
            raise ValueError("只有生成成功的图片可以公开展示")
        if candidate.moderation_status != "normal":
            raise ValueError("已屏蔽图片不能公开展示")
        if not candidate.prompt.strip():
            raise ValueError("缺少用户原始提示词，不能公开展示")

    @staticmethod
    def _has_complete_preview(candidate: ShowcaseCandidate) -> bool:
        return (
            candidate.preview_key is not None
            and candidate.preview_width is not None
            and candidate.preview_height is not None
        )
