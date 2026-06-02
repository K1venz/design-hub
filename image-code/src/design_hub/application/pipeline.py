from dataclasses import dataclass, field
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
from design_hub.ports.metrics import MetricsSink, NoopMetricsSink
from design_hub.ports.model_provider import ProviderError


@dataclass
class GenerationPipeline:
    """引擎脊柱（DIP 集大成）：编排 route→prompt→estimate→守门→生成→fallback。"""

    router: ModelRouter
    orchestrator: PromptOrchestrator
    registry: ProviderRegistry
    estimator: CostEstimator
    guard: CostGuard
    # 生产开启：图生图保真(EDIT)链路拒绝降级到非真实 Provider，避免静默返回 mock 假成功
    # （ISSUE-0007）。默认 False 保持全 Mock dev/CI 行为不变。
    require_live_for_edit: bool = False
    # 业务指标埋点（ISSUE-0008）；默认 noop，生产注入 PrometheusMetricsSink。
    metrics: MetricsSink = field(default_factory=NoopMetricsSink)

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
            used_model, images = await self._generate_with_fallback(brief, prompt, decision, mode)
        except Exception:
            await self.guard.rollback(user_id, estimate)
            raise

        total = sum((img.cost for img in images), Decimal("0"))
        # fallback 后实际模型成本可能 ≠ 主模型预扣，按实际回正 ledger（ISSUE-0009）
        await self.guard.reconcile(user_id, reserved=estimate, actual=total)
        # 业务指标埋点（ISSUE-0008）：出图次数/张数/成本/时延，按模型+模式打标
        self.metrics.record_generation(
            model=used_model.value,
            mode=mode.value,
            image_count=len(images),
            cost=total,
            latency_ms=max((img.latency_ms for img in images), default=0),
        )
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
        mode: GenMode,
    ) -> tuple[ModelName, list[GeneratedImage]]:
        last_error: ProviderError | None = None
        for model in (decision.primary, *decision.fallbacks):
            provider = self.registry.get(model)
            # 保真主链路(EDIT)不接受占位/Mock Provider 的结果：fail-fast，不静默假成功
            if mode is GenMode.EDIT and self.require_live_for_edit and not provider.is_live:
                last_error = ProviderError(
                    f"{model} 非真实 Provider，图生图保真链路拒绝降级（ISSUE-0007）"
                )
                continue
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
