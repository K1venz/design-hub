from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.admin import AdminAction, ModerationStatus
from design_hub.domain.errors import DomainError, NotFoundError
from design_hub.infrastructure.db.models import (
    AdminAuditLogRow,
    ListingImageRow,
    ListingJobRow,
)
from design_hub.ports.showcase import (
    ShowcaseCandidate,
    ShowcasePublication,
    ShowcaseRepository,
)


class SqlAlchemyShowcaseRepository(ShowcaseRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_candidate(self, image_id: int) -> ShowcaseCandidate | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(ListingImageRow, ListingJobRow)
                    .join(ListingJobRow, ListingJobRow.id == ListingImageRow.job_id)
                    .where(ListingImageRow.id == image_id)
                )
            ).one_or_none()
        if row is None:
            return None
        image, job = row
        return self._candidate(image, job)

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
        async with self._session_factory() as session:
            async with session.begin():
                row = (
                    await session.execute(
                        select(ListingImageRow, ListingJobRow)
                        .join(ListingJobRow, ListingJobRow.id == ListingImageRow.job_id)
                        .where(ListingImageRow.id == image_id)
                        .with_for_update()
                    )
                ).one_or_none()
                if row is None:
                    raise NotFoundError("图片不存在")
                image, job = row
                if (
                    image.is_public_showcase == is_public
                    and image.showcase_download_allowed == download_allowed
                ):
                    raise DomainError("公开展示状态没有变化")
                if not is_public and download_allowed:
                    raise ValueError("未公开图片不能允许下载")
                if is_public:
                    self._validate_public(image, job)
                    if (
                        preview_key is None
                        or preview_width is None
                        or preview_height is None
                    ):
                        raise ValueError("公开展示缺少压缩预览图")

                before = {
                    "is_public_showcase": image.is_public_showcase,
                    "showcase_download_allowed": image.showcase_download_allowed,
                }
                was_public = image.is_public_showcase
                image.is_public_showcase = is_public
                image.showcase_download_allowed = download_allowed
                if preview_key is not None:
                    image.showcase_preview_key = preview_key
                    image.showcase_preview_width = preview_width
                    image.showcase_preview_height = preview_height
                if is_public and not was_public:
                    image.showcased_at = datetime.now(UTC)
                    image.showcased_by = actor_id
                elif not is_public:
                    image.showcased_at = None
                    image.showcased_by = None
                after = {
                    "is_public_showcase": image.is_public_showcase,
                    "showcase_download_allowed": image.showcase_download_allowed,
                }
                session.add(
                    AdminAuditLogRow(
                        id=uuid4().hex,
                        actor_user_id=actor_id,
                        action=AdminAction.IMAGE_SHOWCASE_UPDATE.value,
                        target_type="image",
                        target_id=str(image_id),
                        before=before,
                        after=after,
                        reason=None,
                    )
                )
                await session.flush()
                result = ShowcasePublication(
                    image_id=image.id,
                    is_public=image.is_public_showcase,
                    download_allowed=image.showcase_download_allowed,
                    preview_width=image.showcase_preview_width,
                    preview_height=image.showcase_preview_height,
                    showcased_at=image.showcased_at,
                    showcased_by=image.showcased_by,
                )
        return result

    @staticmethod
    def _validate_public(image: ListingImageRow, job: ListingJobRow) -> None:
        if image.status != "成功":
            raise ValueError("只有生成成功的图片可以公开展示")
        if image.moderation_status != ModerationStatus.NORMAL.value:
            raise ValueError("已屏蔽图片不能公开展示")
        if not job.prompt.strip():
            raise ValueError("缺少用户原始提示词，不能公开展示")

    @staticmethod
    def _candidate(
        image: ListingImageRow,
        job: ListingJobRow,
    ) -> ShowcaseCandidate:
        return ShowcaseCandidate(
            image_id=image.id,
            image_key=image.image_key,
            status=image.status,
            moderation_status=image.moderation_status,
            prompt=job.prompt,
            is_public=image.is_public_showcase,
            download_allowed=image.showcase_download_allowed,
            preview_key=image.showcase_preview_key,
            preview_width=image.showcase_preview_width,
            preview_height=image.showcase_preview_height,
        )
