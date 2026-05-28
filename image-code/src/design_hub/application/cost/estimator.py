from decimal import Decimal

from design_hub.domain.models import RoutingDecision
from design_hub.ports.model_provider import AbstractModelProvider


class CostEstimator:
    def estimate(self, decision: RoutingDecision, provider: AbstractModelProvider) -> Decimal:
        return provider.unit_cost * decision.candidate_count
