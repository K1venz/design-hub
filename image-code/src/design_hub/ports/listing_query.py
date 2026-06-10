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
    image_type: str | None = None  # 白底|场景|卖点；None=单图流（PRD §3.12.14）


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
    # 爆款复刻（PRD §3.13）：档位（None=非复刻）+ 输入图角色（与 input_keys 同序；None=旧数据）
    clone_mode: str | None = None
    input_roles: tuple[str | None, ...] = ()


class ListingHistoryQuery(ABC):
    """listing 历史读侧端口（CQRS，独立于写侧 ListingHistory）。user_id 隔离：只返回本人任务。"""

    @abstractmethod
    async def list_jobs(
        self, *, user_id: str, limit: int, offset: int, q: str | None = None
    ) -> list[ListingJobSummary]:
        """q 非空 → 按 prompt / platform 模糊匹配（仍限本人、时间倒序、分页）。"""
        ...

    @abstractmethod
    async def get_job(self, *, job_id: str, user_id: str) -> ListingJobDetail | None:
        """非本人或不存在 → None（路由映射 404，不泄露存在性）。"""
        ...
