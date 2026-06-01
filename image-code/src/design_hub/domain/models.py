from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from design_hub.domain.enums import (
    AssetKind,
    Category,
    JobStatus,
    ModelName,
    ProjectStatus,
    Style,
    SubScene,
    TaskEventType,
    TemplateFamily,
    Tier,
)


@dataclass(frozen=True)
class GeneratedImage:
    url: str
    seed: int
    latency_ms: int
    cost: Decimal


@dataclass(frozen=True)
class PromptPair:
    positive: str
    negative: str


@dataclass(frozen=True)
class RoutingDecision:
    primary: ModelName
    fallbacks: tuple[ModelName, ...]
    candidate_count: int


@dataclass(frozen=True)
class ProductVisualInfo:
    product_type: str
    main_color_hex: str
    material: str
    shape_ratio: str
    logo_position: str


@dataclass(frozen=True)
class Brief:
    customer: str
    subscene: SubScene
    family: TemplateFamily
    tier: Tier
    style: Style
    category: Category
    size: tuple[int, int]
    n: int = 6
    copy_text: str | None = None
    taboo: str | None = None
    product_desc: str | None = None
    brand_name: str | None = None
    reference_images: tuple[bytes, ...] = ()


@dataclass(frozen=True)
class GenerationResult:
    job_prompt: PromptPair
    decision: RoutingDecision
    used_model: ModelName
    images: tuple[GeneratedImage, ...]
    total_cost: Decimal


@dataclass(frozen=True)
class BudgetSnapshot:
    user_month_used: Decimal
    user_monthly_quota: Decimal
    company_month_used: Decimal
    company_monthly_budget: Decimal


@dataclass(frozen=True)
class JobRecord:
    """已持久化出图任务的读模型。"""

    id: str
    user_id: str
    customer: str
    used_model: ModelName
    total_cost: Decimal
    status: JobStatus
    images: tuple[GeneratedImage, ...]


@dataclass(frozen=True)
class TaskEvent:
    """异步出图任务的进度事件（PRD §6.3.1）。"""

    job_id: str
    type: TaskEventType
    data: dict[str, Any]


@dataclass(frozen=True)
class CustomerRecord:
    """客户档案读模型。"""

    id: int
    name: str
    contact: str | None
    industry: str | None
    brand_color: str | None
    common_styles: tuple[str, ...]
    common_taboos: tuple[str, ...]
    common_sizes: tuple[str, ...]


@dataclass(frozen=True)
class ProjectRecord:
    """项目读模型（一单一档）。"""

    id: int
    customer_id: int
    name: str
    status: ProjectStatus
    current_round: int


@dataclass(frozen=True)
class BriefRecord:
    """标准化需求单读模型（PRD 8 字段，多选；D2 方案①：不含 family/品类/子场景/档位）。"""

    id: int
    project_id: int
    material_types: tuple[str, ...]
    sizes: tuple[str, ...]
    styles: tuple[str, ...]
    resolution: str | None
    bleed: str | None
    copy_text: str | None
    taboo: str | None
    delivery: dict[str, Any]


@dataclass(frozen=True)
class AssetRecord:
    """项目素材读模型（产品图/参考图）。"""

    id: int
    project_id: int
    kind: AssetKind
    url: str


@dataclass(frozen=True)
class GenerationConfig:
    """出图配置（D2 方案①：出图时单独提交，不入需求单表）。

    单值的 family/品类/子场景/档位/尺寸/风格 + 候选数 + 选中素材，
    与需求单(copy_text/taboo)、素材字节合成域 Brief。
    """

    subscene: SubScene
    family: TemplateFamily
    category: Category
    tier: Tier
    style: Style
    size: tuple[int, int]
    n: int = 6
    asset_ids: tuple[int, ...] = ()
