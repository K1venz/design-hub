from decimal import Decimal

from pydantic import BaseModel, Field

from design_hub.application.cost.preview import CostPreview
from design_hub.domain.enums import (
    Category,
    ModelName,
    Style,
    SubScene,
    TemplateFamily,
    Tier,
)
from design_hub.domain.models import Brief, GenerationResult


class GenerateRequest(BaseModel):
    """HTTP 边界输入；负责把传输层 DTO 翻译成领域 Brief（边界即校验点）。"""

    customer: str
    subscene: SubScene
    family: TemplateFamily
    tier: Tier
    style: Style
    category: Category
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    n: int = Field(default=6, ge=1)
    copy_text: str | None = None
    taboo: str | None = None
    product_desc: str | None = None
    brand_name: str | None = None

    def to_brief(self) -> Brief:
        return Brief(
            customer=self.customer,
            subscene=self.subscene,
            family=self.family,
            tier=self.tier,
            style=self.style,
            category=self.category,
            size=(self.width, self.height),
            n=self.n,
            copy_text=self.copy_text,
            taboo=self.taboo,
            product_desc=self.product_desc,
            brand_name=self.brand_name,
        )


class GeneratedImageOut(BaseModel):
    url: str
    seed: int
    latency_ms: int
    cost: Decimal


class GenerateResponse(BaseModel):
    used_model: ModelName
    total_cost: Decimal
    positive_prompt: str
    negative_prompt: str
    images: list[GeneratedImageOut]

    @classmethod
    def from_result(cls, result: GenerationResult) -> "GenerateResponse":
        return cls(
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


class CostPreviewResponse(BaseModel):
    tier: Tier
    candidate_count: int
    model: ModelName
    estimated_cost: Decimal
    month_used: Decimal
    month_budget: Decimal

    @classmethod
    def from_preview(cls, preview: CostPreview) -> "CostPreviewResponse":
        return cls(
            tier=preview.tier,
            candidate_count=preview.candidate_count,
            model=preview.model,
            estimated_cost=preview.estimated_cost,
            month_used=preview.month_used,
            month_budget=preview.month_budget,
        )
