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
    edit_mode: str | None = None  # delta|full；None=原生单（列表 ✎ 徽标，PRD §3.12.13 B③）


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
    # 二次编辑（PRD §3.12.13/ISSUE-0040）：迭代链回显（None=非编辑单）
    parent_job_id: str | None = None
    edit_mode: str | None = None
    source_image_key: str | None = None  # Out 层签 url 作「改自这张」回显
    source_image_type: str | None = None  # 源张图型（「改自·场景图」徽标）
    chain_cost: Decimal | None = None  # 迭代链累计：根计源张单张 cost（R5）+ 路径编辑单成本


@dataclass(frozen=True)
class EditSource:
    """编辑源图反解结果（ISSUE-0040 写路径校验）：一次反解出全部父上下文。"""

    parent_job_id: str
    parent_ratio: str
    parent_modifiers: dict[str, str]
    root_product_upload_keys: tuple[str, ...]  # 链根产品锚 1..3（uploads 桶）


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

    @abstractmethod
    async def resolve_edit_source(
        self, *, source_image_key: str, user_id: str
    ) -> EditSource | None:
        """二次编辑反解（E-δ）：key→源行(本人∧成功∧最新)→父 job→沿链核 owner→链根产品锚。

        任一环不满足 → None（路由 404 anti-enum，不区分 不存在/他人/失败张）。
        """
        ...
