"""领域层：实体、值对象、枚举与领域错误（零外部依赖）。"""

from design_hub.domain.enums import (
    Category,
    MaterialType,
    ModelName,
    Style,
    SubScene,
    TemplateFamily,
    Tier,
)
from design_hub.domain.errors import BudgetExceeded, DomainError
from design_hub.domain.models import (
    Brief,
    BudgetSnapshot,
    GeneratedImage,
    GenerationResult,
    ProductVisualInfo,
    PromptPair,
    RoutingDecision,
)

__all__ = [
    "Brief",
    "BudgetExceeded",
    "BudgetSnapshot",
    "Category",
    "DomainError",
    "GeneratedImage",
    "GenerationResult",
    "MaterialType",
    "ModelName",
    "ProductVisualInfo",
    "PromptPair",
    "RoutingDecision",
    "Style",
    "SubScene",
    "TemplateFamily",
    "Tier",
]
