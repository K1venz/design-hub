from collections import defaultdict
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.admin import AdminAction, ModerationStatus
from design_hub.domain.errors import DataInvariantError, DomainError, NotFoundError
from design_hub.infrastructure.db.models import (
    AdminAuditLogRow,
    ListingImageRow,
    ListingJobRow,
)
from design_hub.ports.showcase import (
    PublicShowcaseItem,
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

    async def list_public(self) -> tuple[PublicShowcaseItem, ...]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(ListingImageRow, ListingJobRow)
                    .join(ListingJobRow, ListingJobRow.id == ListingImageRow.job_id)
                    .where(
                        ListingImageRow.is_public_showcase.is_(True),
                        ListingImageRow.moderation_status == ModerationStatus.NORMAL.value,
                        ListingImageRow.status == "成功",
                        ListingImageRow.showcase_preview_key.is_not(None),
                        ListingImageRow.showcase_preview_width.is_not(None),
                        ListingImageRow.showcase_preview_height.is_not(None),
                        ListingImageRow.image_type.is_not(None),
                        ListingJobRow.category.is_not(None),
                    )
                    .order_by(
                        desc(ListingImageRow.showcased_at),
                        desc(ListingImageRow.id),
                    )
                )
            ).all()
            if not rows:
                return ()
            job_ids = {job.id for _, job in rows}
            plan_rows = (
                await session.execute(
                    select(ListingImageRow.job_id, ListingImageRow.image_type)
                    .where(
                        ListingImageRow.job_id.in_(job_ids),
                        ListingImageRow.status == "成功",
                        ListingImageRow.image_type.in_(("白底", "场景", "卖点")),
                    )
                )
            ).all()

        plans: dict[str, dict[str, int]] = defaultdict(dict)
        for job_id, image_type in plan_rows:
            assert image_type is not None
            plan = plans[job_id]
            plan[image_type] = plan.get(image_type, 0) + 1

        items: list[PublicShowcaseItem] = []
        for image, job in rows:
            assert image.showcase_preview_key is not None
            assert image.showcase_preview_width is not None
            assert image.showcase_preview_height is not None
            assert image.image_type is not None
            assert job.category is not None
            modifiers = self._public_modifiers(job.modifiers)
            items.append(
                PublicShowcaseItem(
                    image_id=image.id,
                    preview_key=image.showcase_preview_key,
                    image_type=image.image_type,
                    prompt=job.prompt,
                    download_allowed=image.showcase_download_allowed,
                    width=image.showcase_preview_width,
                    height=image.showcase_preview_height,
                    category=job.category,
                    ratio=job.ratio,
                    plan=plans[job.id],
                    modifiers=modifiers,
                )
            )
        return tuple(items)

    async def get_download_key(self, image_id: int) -> str | None:
        async with self._session_factory() as session:
            return cast(
                str | None,
                await session.scalar(
                    select(ListingImageRow.image_key).where(
                        ListingImageRow.id == image_id,
                        ListingImageRow.is_public_showcase.is_(True),
                        ListingImageRow.showcase_download_allowed.is_(True),
                        ListingImageRow.moderation_status
                        == ModerationStatus.NORMAL.value,
                        ListingImageRow.status == "成功",
                    )
                )
            )

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
            image_type=image.image_type,
            status=image.status,
            moderation_status=image.moderation_status,
            prompt=job.prompt,
            category=job.category,
            ratio=job.ratio,
            modifiers=job.modifiers,
            is_public=image.is_public_showcase,
            download_allowed=image.showcase_download_allowed,
            preview_key=image.showcase_preview_key,
            preview_width=image.showcase_preview_width,
            preview_height=image.showcase_preview_height,
        )

    @staticmethod
    def _public_modifiers(values: dict[str, object]) -> dict[str, str]:
        result: dict[str, str] = {}
        for key, value in values.items():
            if not isinstance(value, str):
                raise DataInvariantError("公开展示配方参数无效")
            result[key] = value
        return result
