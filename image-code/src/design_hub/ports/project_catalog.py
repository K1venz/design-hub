"""项目级出图任务/候选图列举端口（ISSUE-0012，CQRS 读侧，DIP）。

前端选稿(FE-3)/导出(FE-5) 需据 project_id 枚举其任务与候选图（job_id 不再只来自
出图同步响应）。数据：generation_job.project_id + generated_image.job_id。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class ProjectJob:
    job_id: str
    round_no: int
    subscene: str
    family: str
    tier: str
    category: str
    used_model: str
    candidate_count: int
    total_cost: Decimal
    status: str
    created_at: datetime


@dataclass(frozen=True)
class ProjectImage:
    image_id: int
    job_id: str
    url: str
    seed: int
    score: int | None
    kept: bool
    round_no: int  # 来自所属 job
    subscene: str


class ProjectCatalogQuery(ABC):
    @abstractmethod
    async def jobs(self, project_id: int, *, round_no: int | None = None) -> list[ProjectJob]:
        ...

    @abstractmethod
    async def images(
        self, project_id: int, *, round_no: int | None = None, kept: bool | None = None
    ) -> list[ProjectImage]:
        ...
