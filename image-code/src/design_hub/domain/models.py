from dataclasses import dataclass
from decimal import Decimal

from design_hub.domain.enums import (
    Category,
    JobStatus,
    ModelName,
    Style,
    SubScene,
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
