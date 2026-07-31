from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from design_hub.domain.admin import ModerationReason, ModerationStatus
from design_hub.domain.enums import Role
from design_hub.domain.errors import NotFoundError
from design_hub.ports.admin_console import (
    AdminAuditEntry,
    AdminAuditFilter,
    AdminConsoleRepository,
    AdminImageFilter,
    AdminImageSummary,
    AdminJobDetail,
    AdminJobFilter,
    AdminJobImage,
    AdminJobSummary,
    AdminOverview,
    AdminUserDetail,
    AdminUserFilter,
    AdminUserSummary,
    DateRange,
    ModelCallDetail,
    ModelCallFilter,
    ModelCallSummary,
    Page,
)

_MAX_PAGE_SIZE = 100
_MAX_RANGE = timedelta(days=366)


@dataclass(frozen=True)
class AdminConsoleService:
    repository: AdminConsoleRepository

    @staticmethod
    def date_range(
        *,
        start: datetime | None,
        end: datetime | None,
        default_days: int | None = None,
    ) -> DateRange | None:
        if start is None and end is None:
            if default_days is None:
                return None
            end = datetime.now(UTC)
            start = end - timedelta(days=default_days)
        elif start is None or end is None:
            raise ValueError("start 和 end 必须同时提供")
        assert start is not None and end is not None
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("时间范围必须包含时区")
        start = start.astimezone(UTC)
        end = end.astimezone(UTC)
        if start >= end:
            raise ValueError("start 必须早于 end")
        if end - start > _MAX_RANGE:
            raise ValueError("时间范围不能超过 366 天")
        return DateRange(start=start, end=end)

    @staticmethod
    def page(*, limit: int, offset: int) -> tuple[int, int]:
        if limit < 1 or limit > _MAX_PAGE_SIZE:
            raise ValueError("limit 必须在 1 到 100 之间")
        if offset < 0:
            raise ValueError("offset 不能为负数")
        return limit, offset

    async def overview(self, date_range: DateRange) -> AdminOverview:
        return await self.repository.overview(date_range)

    async def list_users(
        self,
        *,
        q: str | None,
        role: Role | None,
        enabled: bool | None,
        limit: int,
        offset: int,
    ) -> Page[AdminUserSummary]:
        limit, offset = self.page(limit=limit, offset=offset)
        q = self._text(q, max_length=100)
        return await self.repository.list_users(
            AdminUserFilter(q=q, role=role, enabled=enabled),
            limit=limit,
            offset=offset,
        )

    async def get_user(self, user_id: int) -> AdminUserDetail:
        user = await self.repository.get_user(user_id)
        if user is None:
            raise NotFoundError("用户不存在")
        return user

    async def list_jobs(
        self,
        filters: AdminJobFilter,
        *,
        limit: int,
        offset: int,
    ) -> Page[AdminJobSummary]:
        limit, offset = self.page(limit=limit, offset=offset)
        return await self.repository.list_jobs(
            filters,
            limit=limit,
            offset=offset,
        )

    async def get_job(self, job_id: str) -> AdminJobDetail:
        job_id = self._required_text(job_id, max_length=32)
        job = await self.repository.get_job(job_id)
        if job is None:
            raise NotFoundError("任务不存在")
        return job

    async def list_images(
        self,
        filters: AdminImageFilter,
        *,
        limit: int,
        offset: int,
    ) -> Page[AdminImageSummary]:
        limit, offset = self.page(limit=limit, offset=offset)
        return await self.repository.list_images(
            filters,
            limit=limit,
            offset=offset,
        )

    async def summarize_model_calls(
        self,
        filters: ModelCallFilter,
    ) -> tuple[ModelCallSummary, ...]:
        return await self.repository.summarize_model_calls(filters)

    async def list_model_calls(
        self,
        filters: ModelCallFilter,
        *,
        limit: int,
        offset: int,
    ) -> Page[ModelCallDetail]:
        limit, offset = self.page(limit=limit, offset=offset)
        return await self.repository.list_model_calls(
            filters,
            limit=limit,
            offset=offset,
        )

    async def list_audit_logs(
        self,
        filters: AdminAuditFilter,
        *,
        limit: int,
        offset: int,
    ) -> Page[AdminAuditEntry]:
        limit, offset = self.page(limit=limit, offset=offset)
        return await self.repository.list_audit_logs(
            filters,
            limit=limit,
            offset=offset,
        )

    async def set_image_moderation(
        self,
        *,
        actor_id: int,
        image_id: int,
        status: ModerationStatus,
        reason: ModerationReason | None,
        note: str | None,
    ) -> AdminJobImage:
        if image_id < 1:
            raise ValueError("image_id 必须为正整数")
        normalized_note = self._text(note, max_length=500)
        if status is ModerationStatus.BLOCKED:
            if reason is None:
                raise ValueError("屏蔽图片必须选择原因")
        else:
            reason = None
            normalized_note = None
        return await self.repository.set_image_moderation(
            actor_id=actor_id,
            image_id=image_id,
            status=status,
            reason=reason,
            note=normalized_note,
        )

    @staticmethod
    def _text(value: str | None, *, max_length: int) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if len(value) > max_length:
            raise ValueError(f"筛选文本不能超过 {max_length} 个字符")
        return value

    @classmethod
    def _required_text(cls, value: str, *, max_length: int) -> str:
        normalized = cls._text(value, max_length=max_length)
        if normalized is None:
            raise ValueError("标识不能为空")
        return normalized
