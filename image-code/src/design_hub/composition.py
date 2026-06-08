"""组装根（Composition Root）：唯一允许同时认识 application 与 infrastructure 的地方。

DIP 的落点——把抽象端口绑定到具体适配器都集中在此，其余各层只见抽象。
"""

from collections.abc import Mapping
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
from design_hub.infrastructure.export.local_export_store import LocalExportStore
from design_hub.infrastructure.ledger.memory import InMemoryLedgerRepository
from design_hub.infrastructure.providers.mock import MockModelProvider
from design_hub.infrastructure.providers.openai_compat import OpenAICompatImageProvider
from design_hub.infrastructure.storage.local import LocalImageStore, LocalMediaUrlSigner
from design_hub.infrastructure.storage.local_upload import LocalUploadStore
from design_hub.infrastructure.storage.tos import (
    TosExportStore,
    TosImageStore,
    TosMediaUrlSigner,
    TosUploadStore,
    build_tos_client,
)
from design_hub.infrastructure.vision.mock import MockVisionAssist
from design_hub.ports.exporter import ExportStore
from design_hub.ports.image_store import ImageStore
from design_hub.ports.ledger import LedgerRepository
from design_hub.ports.media_url_signer import MediaUrlSigner
from design_hub.ports.model_config_repository import ModelConfigRecord
from design_hub.ports.upload_store import UploadStore

# Mock 单价对齐 PRD §3.5 参考价（默认/兜底价；真实单价由 model_config 表热更覆盖，见 WP-H）
_MOCK_UNIT_COSTS: dict[ModelName, Decimal] = {
    ModelName.SEEDREAM_5: Decimal("0.20"),
    # base 上线档($0.05实扣)；¥0.40=锁汇率~7.2的¥占位估算(非真实账单,季度复核)
    ModelName.GPT_IMAGE_2: Decimal("0.40"),
    ModelName.WANXIANG_27: Decimal("0.05"),
    ModelName.LINGDONG_2: Decimal("0.04"),
}


def default_model_configs() -> list[ModelConfigRecord]:
    """默认 5 模型配置（启动 seed 用）：单价取 _MOCK_UNIT_COSTS，默认启用。"""
    return [
        ModelConfigRecord(name=name.value, unit_cost=cost, enabled=True, extra={})
        for name, cost in _MOCK_UNIT_COSTS.items()
    ]


@dataclass
class Engine:
    """对外暴露的两个用例入口：出图 pipeline 与成本预估 preview。"""

    pipeline: GenerationPipeline
    preview: CostPreviewService


def build_mock_registry(
    unit_costs: Mapping[ModelName, Decimal] | None = None,
) -> ProviderRegistry:
    """Mock 全模型。unit_costs（来自 model_config 表）覆盖默认价，缺失项回落 Mock 兜底。"""
    costs = {**_MOCK_UNIT_COSTS, **(unit_costs or {})}
    registry = ProviderRegistry()
    for name, unit_cost in costs.items():
        registry.register(MockModelProvider(name=name, unit_cost=unit_cost))
    return registry


def build_gpt_image_provider(
    settings: Settings, unit_costs: Mapping[ModelName, Decimal] | None = None
) -> OpenAICompatImageProvider:
    """真实 gpt-image-2 中转 Provider（apinebula/诗云）。需 .env 提供 GPT_IMAGE_*。

    单价优先取 model_config 表（unit_costs），缺失则回落 ¥占位估算（与 seed 一致）。
    b64 出图经 LocalImageStore 落本地目录（A 方案）；将来换 OSS 只改 image_store。
    """
    if not settings.gpt_image_base_url or not settings.gpt_image_model:
        raise ValueError("GPT_IMAGE_BASE_URL / GPT_IMAGE_MODEL 未配置（见 .env）")
    unit_cost = (unit_costs or {}).get(ModelName.GPT_IMAGE_2, Decimal("0.40"))
    return OpenAICompatImageProvider(
        name=ModelName.GPT_IMAGE_2,
        unit_cost=unit_cost,
        base_url=settings.gpt_image_base_url,
        # 多 key：GPT_IMAGE_API_KEY 逗号分隔；provider 按请求 round-robin 分发（缓解单 key 限流）
        api_keys=[
            k.strip() for k in settings.gpt_image_api_key.get_secret_value().split(",") if k.strip()
        ],
        model=settings.gpt_image_model,
        image_store=build_image_store(settings),
        trust_env=False,  # 境内中转站直连，绕开本机梯子代理
        timeout=300.0,  # 图生图 edit 实测 ~187s（ISSUE-0007），180s 太紧；放宽到 300s 留余量
        max_retries=2,  # 中转站 edit 端点间歇 500"系统繁忙"，瞬时错误重试（ISSUE-0007）
    )


def _tos_enabled(settings: Settings) -> bool:
    return bool(
        settings.tos_access_key.get_secret_value()
        and settings.tos_generate_bucket
        and settings.tos_upload_bucket
    )


def build_media_signer(settings: Settings) -> MediaUrlSigner:
    """配了 TOS → 预签名 url 签名器；否则本地静态拼接（nginx /img，ISSUE-0029）。"""
    if _tos_enabled(settings):
        return TosMediaUrlSigner(
            build_tos_client(settings),
            settings.tos_generate_bucket,
            settings.tos_upload_bucket,
            settings.tos_signed_url_ttl,
        )
    return LocalMediaUrlSigner(settings.image_public_base_url)


def build_image_store(settings: Settings) -> ImageStore:
    """出图结果落点：配了 TOS → generate 桶；否则本地目录。"""
    if _tos_enabled(settings):
        return TosImageStore(
            build_tos_client(settings),
            settings.tos_generate_bucket,
            build_media_signer(settings),
        )
    return LocalImageStore(
        settings.image_output_dir, public_base_url=settings.image_public_base_url
    )


def build_upload_store(settings: Settings) -> UploadStore:
    """上传图落点：配了 TOS → upload 桶；否则本地 assets/ 目录。"""
    if _tos_enabled(settings):
        return TosUploadStore(build_tos_client(settings), settings.tos_upload_bucket)
    return LocalUploadStore(settings.asset_output_dir)


def build_export_store(settings: Settings) -> ExportStore:
    """导出读源图：配 TOS → generate 桶读（ISSUE-0034）；否则本地。产物落本地导出目录。"""
    if _tos_enabled(settings):
        return TosExportStore(
            build_tos_client(settings), settings.tos_generate_bucket, settings.export_output_dir
        )
    return LocalExportStore(settings.export_output_dir, source_dir=settings.image_output_dir)


def build_registry(
    settings: Settings,
    *,
    real_gpt_image: bool = False,
    unit_costs: Mapping[ModelName, Decimal] | None = None,
) -> ProviderRegistry:
    """Mock 全模型；real_gpt_image=True 时用真实 Provider 覆盖 GPT_IMAGE_2。

    unit_costs（model_config 真实单价）注入 Provider，替换写死的 Mock 价；缺失回落兜底。
    仅 gpt-image 有真实 key，其余模型暂仍 Mock；按 LSP 替换，路由/pipeline 无感。
    """
    registry = build_mock_registry(unit_costs)
    if real_gpt_image:
        registry.register(build_gpt_image_provider(settings, unit_costs))  # 按 name 覆盖 Mock
    return registry


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
    real_gpt_image: bool = False,
    settings: Settings | None = None,
    unit_costs: Mapping[ModelName, Decimal] | None = None,
) -> Engine:
    """装配引擎。默认全 Mock（零基础设施）；真实适配器由调用方传入替换（LSP）。

    real_gpt_image=True → GPT_IMAGE_2 走真实中转 Provider（需 .env 配 GPT_IMAGE_*）。
    unit_costs（model_config 真实单价）注入 Provider，缺省则用 Mock 兜底价。
    """
    if registry is None:
        registry = build_registry(
            settings or Settings(), real_gpt_image=real_gpt_image, unit_costs=unit_costs
        )
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
