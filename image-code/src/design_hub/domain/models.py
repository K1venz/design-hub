from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from design_hub.domain.enums import ModelName, Role, TaskEventType


@dataclass(frozen=True)
class GeneratedImage:
    url: str
    seed: int
    latency_ms: int
    cost: Decimal
    image_type: str | None = None  # 套图图型（白底|场景|卖点）；None=单图流（PRD §3.12.14）


@dataclass(frozen=True)
class ListingResult:
    """listing 轻量出图结果（出图用例返回值）。"""

    prompt: str
    used_model: ModelName
    images: tuple[GeneratedImage, ...]
    total_cost: Decimal
    # 套图部分失败明细（图型, 原因摘要）；单图流恒空（失败仍走整单 TASK_FAILED 语义）
    failures: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ListingJobImage:
    """listing 历史持久化：单张候选图（image_key=文件名，不存绝对 url）。"""

    image_key: str
    seed: int
    cost: Decimal
    status: str  # 成功 | 失败
    image_type: str | None = None  # 白底|场景|卖点；None=单图流


@dataclass(frozen=True)
class ListingJobOutcome:
    """listing 一次出图任务的可持久化快照（ISSUE-0030，写历史用）。"""

    job_id: str
    user_id: str
    prompt: str
    modifiers: dict[str, str]
    ratio: str
    size: str  # 形如 1024x1536
    n: int
    status: str  # 完成 | 部分完成 | 失败
    total_cost: Decimal
    error: str | None
    images: tuple[ListingJobImage, ...]
    upload_keys: tuple[str, ...]
    # 爆款复刻（PRD §3.13）：档位（参考风格|高度复刻；None=非复刻）+ 输入图角色
    # （product|reference，与 upload_keys 同序对齐；空=旧行为全 None）
    clone_mode: str | None = None
    input_roles: tuple[str, ...] = ()
    # 二次编辑（PRD §3.12.13/ISSUE-0040）：迭代链（None=非编辑单）。源图经
    # source_image_key 回显（在 generate 桶、不进 upload_keys）；编辑单的
    # upload_keys=链根产品锚（role=product）。
    parent_job_id: str | None = None
    source_image_key: str | None = None
    edit_mode: str | None = None  # delta|full


@dataclass(frozen=True)
class BudgetSnapshot:
    user_month_used: Decimal
    user_monthly_quota: Decimal
    company_month_used: Decimal
    company_monthly_budget: Decimal


@dataclass(frozen=True)
class TaskEvent:
    """异步出图任务的进度事件（PRD §6.3.1）。"""

    job_id: str
    type: TaskEventType
    data: dict[str, Any]


@dataclass(frozen=True)
class AuthUser:
    """已认证用户（JWT 载荷读模型）。"""

    user_id: str
    name: str
    role: Role
    dept: str | None = None
