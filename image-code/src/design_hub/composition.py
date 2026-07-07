"""组装根（Composition Root）：唯一允许同时认识 application 与 infrastructure 的地方。

DIP 的落点——把抽象端口绑定到具体适配器都集中在此，其余各层只见抽象。
2026-06-09 旧海报/项目出图流下线（ISSUE-0039）后，仅保留 listing 主线所需的装配
（registry / 图床签名 / 上传落点 / 真实 gpt provider）。
"""

from collections.abc import Mapping
from decimal import Decimal

from design_hub.application.registry import ProviderRegistry
from design_hub.config.settings import Settings
from design_hub.domain.enums import ModelName
from design_hub.infrastructure.providers.mock import MockModelProvider
from design_hub.infrastructure.providers.mock_text import MockTextLLMProvider
from design_hub.infrastructure.providers.openai_compat import OpenAICompatImageProvider
from design_hub.infrastructure.providers.openai_compat_text import OpenAICompatTextProvider
from design_hub.infrastructure.storage.local import LocalImageStore, LocalMediaUrlSigner
from design_hub.infrastructure.storage.local_upload import LocalUploadStore
from design_hub.infrastructure.storage.tos import (
    TosImageStore,
    TosMediaUrlSigner,
    TosUploadStore,
    build_tos_client,
)
from design_hub.ports.image_store import ImageStore
from design_hub.ports.media_url_signer import MediaUrlSigner
from design_hub.ports.model_config_repository import ModelConfigRecord
from design_hub.ports.text_llm import TextLLMPort
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
        # 瞬时错误重试（ISSUE-0007 间歇 500 + ISSUE-0047 套图并发 429）：加大余量 + 抖动退避
        max_retries=settings.gpt_image_max_retries,
        retry_backoff=settings.gpt_image_retry_backoff,
        retry_max_sleep=settings.gpt_image_retry_max_sleep,
        retry_max_elapsed=settings.gpt_image_retry_max_elapsed,  # 总重试墙钟（ISSUE-0055 (i)）
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


def build_text_llm(settings: Settings) -> TextLLMPort:
    """文本 LLM（方案 C「帮我设计」Agent）：配了 TEXT_LLM_* → 真实 OpenAI 兼容适配器；否则 Mock。

    ⚠️ 现有 GPT_IMAGE key 仅图像权限组（探明实测：文本模型 403 no access）；文本需用户
    另开 key/access（apinebula 开文本权限或单独接 DeepSeek）。未配 → Mock 全链可联调。
    """
    key = settings.text_llm_api_key.get_secret_value()
    if key and settings.text_llm_base_url and settings.text_llm_model:
        # ARK thinking 模型关思考提速（结构化选工具正确性不降、延迟 13.8s→3.5s）；
        # 通用供应商默认不透传，由 .env TEXT_LLM_THINKING_DISABLED 显式开启。
        extra_body = (
            {"thinking": {"type": "disabled"}} if settings.text_llm_thinking_disabled else {}
        )
        return OpenAICompatTextProvider(
            base_url=settings.text_llm_base_url,
            api_key=key,
            model=settings.text_llm_model,
            extra_body=extra_body,
        )
    return MockTextLLMProvider()


def build_registry(
    settings: Settings,
    *,
    real_gpt_image: bool = False,
    unit_costs: Mapping[ModelName, Decimal] | None = None,
) -> ProviderRegistry:
    """Mock 全模型；real_gpt_image=True 时用真实 Provider 覆盖 GPT_IMAGE_2。

    unit_costs（model_config 真实单价）注入 Provider，替换写死的 Mock 价；缺失回落兜底。
    仅 gpt-image 有真实 key，其余模型暂仍 Mock；按 LSP 替换。
    """
    registry = build_mock_registry(unit_costs)
    if real_gpt_image:
        registry.register(build_gpt_image_provider(settings, unit_costs))  # 按 name 覆盖 Mock
    return registry
