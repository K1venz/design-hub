from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from design_hub.application.project.project_generation_service import (
    ProjectGenerationOutcome,
)
from design_hub.domain.enums import (
    AssetKind,
    Category,
    ModelName,
    ProjectStatus,
    Style,
    SubScene,
    TemplateFamily,
    Tier,
)
from design_hub.domain.models import (
    AssetRecord,
    BriefRecord,
    CustomerRecord,
    GenerationConfig,
    ProjectRecord,
)
from design_hub.interface.schemas import GeneratedImageOut


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1)
    contact: str | None = None
    industry: str | None = None
    brand_color: str | None = None
    common_styles: list[str] = Field(default_factory=list)
    common_taboos: list[str] = Field(default_factory=list)
    common_sizes: list[str] = Field(default_factory=list)


class CustomerOut(BaseModel):
    id: int
    name: str
    contact: str | None
    industry: str | None
    brand_color: str | None
    common_styles: list[str]
    common_taboos: list[str]
    common_sizes: list[str]

    @classmethod
    def of(cls, r: CustomerRecord) -> "CustomerOut":
        return cls(
            id=r.id, name=r.name, contact=r.contact, industry=r.industry,
            brand_color=r.brand_color, common_styles=list(r.common_styles),
            common_taboos=list(r.common_taboos), common_sizes=list(r.common_sizes),
        )


class ProjectCreate(BaseModel):
    customer_id: int
    name: str = Field(min_length=1)


class ProjectStatusUpdate(BaseModel):
    status: ProjectStatus


class ProjectOut(BaseModel):
    id: int
    customer_id: int
    name: str
    status: ProjectStatus
    current_round: int

    @classmethod
    def of(cls, r: ProjectRecord) -> "ProjectOut":
        return cls(
            id=r.id, customer_id=r.customer_id, name=r.name,
            status=r.status, current_round=r.current_round,
        )


# --- WP-B 标准化需求单（PRD 8 字段，D2 方案①：不含 family/品类/子场景/档位） ---

class BriefUpsert(BaseModel):
    material_types: list[str] = Field(default_factory=list)
    sizes: list[str] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)
    resolution: str | None = None
    bleed: str | None = None
    copy_text: str | None = None
    taboo: str | None = None
    delivery: dict[str, Any] = Field(default_factory=dict)


class BriefOut(BaseModel):
    id: int
    project_id: int
    material_types: list[str]
    sizes: list[str]
    styles: list[str]
    resolution: str | None
    bleed: str | None
    copy_text: str | None
    taboo: str | None
    delivery: dict[str, Any]

    @classmethod
    def of(cls, r: BriefRecord) -> "BriefOut":
        return cls(
            id=r.id, project_id=r.project_id,
            material_types=list(r.material_types), sizes=list(r.sizes),
            styles=list(r.styles), resolution=r.resolution, bleed=r.bleed,
            copy_text=r.copy_text, taboo=r.taboo, delivery=dict(r.delivery),
        )


class AssetOut(BaseModel):
    id: int
    project_id: int
    kind: AssetKind
    url: str

    @classmethod
    def of(cls, r: AssetRecord) -> "AssetOut":
        return cls(id=r.id, project_id=r.project_id, kind=r.kind, url=r.url)


# --- WP-B 项目下出图：出图配置(单值) → 域 Brief 由 brief_to_brief 合成 ---

class ProjectGenerateRequest(BaseModel):
    """出图配置（D2 方案①）。HTTP 边界翻译成 GenerationConfig；需求单/素材后端补齐。"""

    subscene: SubScene
    family: TemplateFamily
    category: Category
    tier: Tier
    style: Style
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    n: int = Field(default=6, ge=1)
    asset_ids: list[int] = Field(default_factory=list)

    def to_config(self) -> GenerationConfig:
        return GenerationConfig(
            subscene=self.subscene,
            family=self.family,
            category=self.category,
            tier=self.tier,
            style=self.style,
            size=(self.width, self.height),
            n=self.n,
            asset_ids=tuple(self.asset_ids),
        )


class ProjectGenerateResponse(BaseModel):
    job_id: str
    project_id: int
    round_no: int
    used_model: ModelName
    total_cost: Decimal
    positive_prompt: str
    negative_prompt: str
    images: list[GeneratedImageOut]

    @classmethod
    def of(cls, outcome: ProjectGenerationOutcome) -> "ProjectGenerateResponse":
        result = outcome.result
        return cls(
            job_id=outcome.job_id,
            project_id=outcome.project_id,
            round_no=outcome.round_no,
            used_model=result.used_model,
            total_cost=result.total_cost,
            positive_prompt=result.job_prompt.positive,
            negative_prompt=result.job_prompt.negative,
            images=[
                GeneratedImageOut(
                    url=img.url, seed=img.seed, latency_ms=img.latency_ms, cost=img.cost
                )
                for img in result.images
            ],
        )
