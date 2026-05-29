"""组装根（Composition Root）：唯一允许同时认识 application 与 infrastructure 的地方。

DIP 的落点——把抽象端口绑定到具体适配器都集中在此，其余各层只见抽象。
"""

from dataclasses import dataclass
from decimal import Decimal

from design_hub.application.cost.budget import BudgetPolicy
from design_hub.application.cost.estimator import CostEstimator
from design_hub.application.cost.guard import CostGuard
from design_hub.application.cost.preview import CostPreviewService
from design_hub.application.pipeline import GenerationPipeline
from design_hub.application.prompt.brand import BrandNameGenerator
from design_hub.application.prompt.families.registry import FamilyRegistry
from design_hub.application.prompt.libraries.negative import NegativeLibrary
from design_hub.application.prompt.libraries.quality import QualityLibrary
from design_hub.application.prompt.orchestrator import PromptOrchestrator
from design_hub.application.prompt.profiles.registry import (
    CategoryProfileRegistry,
    StylePresetRegistry,
)
from design_hub.application.registry import ProviderRegistry
from design_hub.application.routing.router import ModelRouter
from design_hub.config.settings import Settings
from design_hub.domain.enums import ModelName
from design_hub.infrastructure.ledger.memory import InMemoryLedgerRepository
from design_hub.infrastructure.providers.mock import MockModelProvider
from design_hub.infrastructure.providers.openai_compat import OpenAICompatImageProvider
from design_hub.infrastructure.storage.local import LocalImageStore
from design_hub.infrastructure.vision.mock import MockVisionAssist
from design_hub.ports.ledger import LedgerRepository

# Mock 单价对齐 PRD §3.5 参考价（仅供本地/CI 估算演示，真实单价由 ModelConfig 提供）
_MOCK_UNIT_COSTS: dict[ModelName, Decimal] = {
    ModelName.SEEDREAM_5: Decimal("0.20"),
    ModelName.QWEN_IMAGE_PRO: Decimal("0.10"),
    ModelName.GPT_IMAGE_2: Decimal("1.19"),
    ModelName.WANXIANG_27: Decimal("0.05"),
    ModelName.LINGDONG_2: Decimal("0.04"),
}


@dataclass
class Engine:
    """对外暴露的两个用例入口：出图 pipeline 与成本预估 preview。"""

    pipeline: GenerationPipeline
    preview: CostPreviewService


def build_mock_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    for name, unit_cost in _MOCK_UNIT_COSTS.items():
        registry.register(MockModelProvider(name=name, unit_cost=unit_cost))
    return registry


def build_gpt_image_provider(settings: Settings) -> OpenAICompatImageProvider:
    """真实 gpt-image-2 中转 Provider（apinebula/诗云）。需 .env 提供 GPT_IMAGE_*。

    b64 出图经 LocalImageStore 落本地目录（A 方案）；将来换 OSS 只改 image_store。
    """
    if not settings.gpt_image_base_url or not settings.gpt_image_model:
        raise ValueError("GPT_IMAGE_BASE_URL / GPT_IMAGE_MODEL 未配置（见 .env）")
    return OpenAICompatImageProvider(
        name=ModelName.GPT_IMAGE_2,
        unit_cost=Decimal("0.10"),  # apinebula gpt-image-2-vip 实扣参考
        base_url=settings.gpt_image_base_url,
        api_key=settings.gpt_image_api_key.get_secret_value(),
        model=settings.gpt_image_model,
        image_store=LocalImageStore(settings.image_output_dir),
        trust_env=False,  # 境内中转站直连，绕开本机梯子代理
    )


def build_orchestrator() -> PromptOrchestrator:
    return PromptOrchestrator(
        families=FamilyRegistry(),
        categories=CategoryProfileRegistry(),
        styles=StylePresetRegistry(),
        negatives=NegativeLibrary(),
        qualities=QualityLibrary(),
        vision=MockVisionAssist(),
        brands=BrandNameGenerator(),
    )


def build_engine(
    *,
    registry: ProviderRegistry | None = None,
    ledger: LedgerRepository | None = None,
) -> Engine:
    """装配引擎。默认全 Mock（零基础设施）；真实适配器由调用方传入替换（LSP）。"""
    registry = registry if registry is not None else build_mock_registry()
    ledger = ledger if ledger is not None else InMemoryLedgerRepository()
    router = ModelRouter()
    estimator = CostEstimator()
    # 同一 ledger 实例同时注入守门与预估，保证额度读写一致
    guard = CostGuard(ledger=ledger, policy=BudgetPolicy())
    pipeline = GenerationPipeline(
        router=router,
        orchestrator=build_orchestrator(),
        registry=registry,
        estimator=estimator,
        guard=guard,
    )
    preview = CostPreviewService(
        router=router,
        registry=registry,
        estimator=estimator,
        ledger=ledger,
    )
    return Engine(pipeline=pipeline, preview=preview)
