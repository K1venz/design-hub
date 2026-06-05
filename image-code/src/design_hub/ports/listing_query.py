from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class ListingJobImageView:
    """历史详情里的单张候选图（读模型，存 key 不存 url）。"""

    image_key: str
    seed: int
    cost: Decimal
    status: str


@dataclass(frozen=True)
class ListingJobSummary:
    """历史列表项（含首图 key 供缩略）。"""

    job_id: str
    status: str
    platform: str | None
    ratio: str
    n: int
    total_cost: Decimal
    created_at: datetime
    first_image_key: str | None
    image_count: int


@dataclass(frozen=True)
class ListingJobDetail:
    """历史详情（元数据 + 全部候选图 + 输入图 key）。"""

    job_id: str
    prompt: str
    modifiers: dict[str, str]
    platform: str | None
    ratio: str
    size: str
    n: int
    status: str
    total_cost: Decimal
    error: str | None
    created_at: datetime
    completed_at: datetime | None
    images: tuple[ListingJobImageView, ...]
    input_keys: tuple[str, ...]


class ListingHistoryQuery(ABC):
    """listing 历史读侧端口（CQRS，独立于写侧 ListingHistory）。user_id 隔离：只返回本人任务。"""

    @abstractmethod
    async def list_jobs(
        self, *, user_id: str, limit: int, offset: int
    ) -> list[ListingJobSummary]:
        ...

    @abstractmethod
    async def get_job(self, *, job_id: str, user_id: str) -> ListingJobDetail | None:
        """非本人或不存在 → None（路由映射 404，不泄露存在性）。"""
        ...
