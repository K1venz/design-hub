from dataclasses import dataclass
from decimal import Decimal

from design_hub.application.cost.estimator import CostEstimator
from design_hub.application.registry import ProviderRegistry
from design_hub.application.routing.router import ModelRouter
from design_hub.domain.enums import ModelName, Tier
from design_hub.domain.models import Brief, RoutingDecision
from design_hub.ports.ledger import LedgerRepository


@dataclass(frozen=True)
class CostPreview:
    """出图前成本预估（PRD §3.10）。只读，不预扣、不生成。"""

    tier: Tier
    candidate_count: int
    model: ModelName
    estimated_cost: Decimal
    month_used: Decimal
    month_budget: Decimal


@dataclass
class CostPreviewService:
    """SRP：只回答"这次大概多少钱、本月还剩多少"，与生成/预扣解耦。"""

    router: ModelRouter
    registry: ProviderRegistry
    estimator: CostEstimator
    ledger: LedgerRepository

    async def preview(self, brief: Brief, user_id: str) -> CostPreview:
        routed = self.router.route(brief.family, brief.subscene, brief.tier)
        decision = RoutingDecision(routed.primary, routed.fallbacks, brief.n)
        estimated = self.estimator.estimate(decision, self.registry.get(decision.primary))
        snapshot = await self.ledger.snapshot(user_id)
        return CostPreview(
            tier=brief.tier,
            candidate_count=brief.n,
            model=decision.primary,
            estimated_cost=estimated,
            month_used=snapshot.company_month_used,
            month_budget=snapshot.company_monthly_budget,
        )
