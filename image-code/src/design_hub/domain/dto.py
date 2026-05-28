from dataclasses import dataclass
from decimal import Decimal

from .enums import Category, ModelName, Style, SubScene, TemplateFamily, Tier


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
