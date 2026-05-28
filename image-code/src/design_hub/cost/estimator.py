from decimal import Decimal

from ..domain.dto import RoutingDecision
from ..providers.base import AbstractModelProvider


class CostEstimator:
    def estimate(self, decision: RoutingDecision, provider: AbstractModelProvider) -> Decimal:
        return provider.unit_cost * decision.candidate_count
