from dataclasses import dataclass
from decimal import Decimal

from design_hub.application.cost.estimator import CostEstimator
from design_hub.application.cost.guard import CostGuard
from design_hub.application.prompt.orchestrator import PromptOrchestrator
from design_hub.application.registry import ProviderRegistry
from design_hub.application.routing.router import ModelRouter
from design_hub.application.routing.table import MAX_CANDIDATES
from design_hub.domain.enums import GenMode, ModelName
from design_hub.domain.models import (
    Brief,
    GeneratedImage,
    GenerationResult,
    PromptPair,
    RoutingDecision,
)
from design_hub.ports.model_provider import ProviderError


@dataclass
class GenerationPipeline:
    """引擎脊柱（DIP 集大成）：编排 route→prompt→estimate→守门→生成→fallback。"""

    router: ModelRouter
    orchestrator: PromptOrchestrator
    registry: ProviderRegistry
    estimator: CostEstimator
    guard: CostGuard

    async def run(self, brief: Brief, user_id: str) -> GenerationResult:
        if brief.n > MAX_CANDIDATES:
            raise ValueError(f"候选数 {brief.n} 超过硬上限 {MAX_CANDIDATES}")

        routed = self.router.route(brief.family, brief.subscene, brief.tier)
        decision = RoutingDecision(routed.primary, routed.fallbacks, brief.n)
        # 有参考图 → 图生图 EDIT(追加产品保真约束)，与 Provider 走 /images/edits 一致
        mode = GenMode.EDIT if brief.reference_images else GenMode.TEXT2IMG
        prompt = await self.orchestrator.build(brief, decision.primary, mode)
        estimate = self.estimator.estimate(decision, self.registry.get(decision.primary))

        await self.guard.precheck_and_reserve(user_id, estimate)
        try:
            used_model, images = await self._generate_with_fallback(brief, prompt, decision)
        except Exception:
            await self.guard.rollback(user_id, estimate)
            raise

        total = sum((img.cost for img in images), Decimal("0"))
        return GenerationResult(
            job_prompt=prompt,
            decision=decision,
            used_model=used_model,
            images=tuple(images),
            total_cost=total,
        )

    async def _generate_with_fallback(
        self,
        brief: Brief,
        prompt: PromptPair,
        decision: RoutingDecision,
    ) -> tuple[ModelName, list[GeneratedImage]]:
        last_error: ProviderError | None = None
        for model in (decision.primary, *decision.fallbacks):
            provider = self.registry.get(model)
            try:
                images = await provider.generate(
                    prompt=prompt.positive,
                    negative_prompt=prompt.negative,
                    reference_images=list(brief.reference_images),
                    size=brief.size,
                    n=decision.candidate_count,
                )
                return model, images
            except ProviderError as error:  # 网络/IO 域：允许切同档位备选
                last_error = error
        raise last_error if last_error else ProviderError("no provider available")
