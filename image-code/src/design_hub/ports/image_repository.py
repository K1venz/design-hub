# 注解延迟求值：根除方法名遮蔽内置类型的隐患（参见 ISSUE-0004）
from __future__ import annotations

from abc import ABC, abstractmethod

from design_hub.domain.models import GeneratedImageRecord


class GeneratedImageRepository(ABC):
    """候选图仓储端口（DIP）：选稿/评分读写（独立于 ports/repositories.py）。"""

    @abstractmethod
    async def job_exists(self, job_id: str) -> bool:
        ...

    @abstractmethod
    async def list_by_job(self, job_id: str) -> list[GeneratedImageRecord]:
        ...

    @abstractmethod
    async def get(self, image_id: int) -> GeneratedImageRecord | None:
        ...

    @abstractmethod
    async def set_score(self, image_id: int, score: int) -> GeneratedImageRecord:
        ...

    @abstractmethod
    async def set_kept(self, image_id: int, *, kept: bool) -> GeneratedImageRecord:
        ...
