# 注解延迟求值：根除方法名遮蔽内置类型的隐患（参见 ISSUE-0004）
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from design_hub.domain.models import RevisionRecord


class RevisionRepository(ABC):
    """改稿单仓储端口（DIP）：独立于 ports/repositories.py。"""

    @abstractmethod
    async def create(
        self, *, project_id: int, round_no: int, deadline: datetime | None = None
    ) -> RevisionRecord:
        ...

    @abstractmethod
    async def get(self, revision_id: int) -> RevisionRecord | None:
        ...

    @abstractmethod
    async def list_by_project(self, project_id: int) -> list[RevisionRecord]:
        ...

    @abstractmethod
    async def add_item(
        self, revision_id: int, *, text: str, related_image_id: int | None = None
    ) -> RevisionRecord:
        ...

    @abstractmethod
    async def set_item_done(self, revision_id: int, seq: int, *, done: bool) -> RevisionRecord:
        ...

    @abstractmethod
    async def has_open_items(self, project_id: int) -> bool:
        """项目下任意改稿单是否仍有未完成条目（交付强校验用）。"""
        ...
