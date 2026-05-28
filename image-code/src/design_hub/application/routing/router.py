from design_hub.application.routing import table
from design_hub.domain.enums import ModelName, SubScene, TemplateFamily, Tier
from design_hub.domain.models import RoutingDecision


class ModelRouter:
    """模板族×档位 二维路由（OCP：决策全部来自数据表）。"""

    def route(self, family: TemplateFamily, subscene: SubScene, tier: Tier) -> RoutingDecision:
        primary = self._primary(family, subscene, tier)
        return RoutingDecision(
            primary=primary,
            fallbacks=table.FALLBACKS.get(primary, ()),
            candidate_count=table.DEFAULT_CANDIDATES,
        )

    def _primary(self, family: TemplateFamily, subscene: SubScene, tier: Tier) -> ModelName:
        if family in table.FORCED_GPT_FAMILIES:
            return ModelName.GPT_IMAGE_2
        if tier is Tier.REFINE:
            return table.REFINE_MODEL
        if tier is Tier.DRAFT:
            return table.DRAFT_MODEL_S4 if subscene is SubScene.S4 else table.DRAFT_MODEL_DEFAULT
        if family not in table.FAMILY_PRIMARY:
            raise KeyError(f"Template family {family} has no V1 primary model")
        return table.FAMILY_PRIMARY[family]
