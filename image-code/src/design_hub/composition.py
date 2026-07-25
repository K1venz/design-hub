"""组装根（Composition Root）：唯一允许同时认识 application 与 infrastructure 的地方。

DIP 的落点——把抽象端口绑定到具体适配器都集中在此，其余各层只见抽象。
2026-06-09 旧海报/项目出图流下线（ISSUE-0039）后，仅保留 listing 主线所需的装配
（registry / 图床签名 / 上传落点 / 真实 gpt provider）。
"""

import os
from collections.abc import Mapping
from decimal import Decimal

from design_hub.application.registry import ProviderRegistry
from design_hub.config.settings import Settings
from design_hub.domain.enums import ModelName
from design_hub.infrastructure.auth.rsa_cipher import RsaPasswordCipher
from design_hub.infrastructure.providers.api_key_pool import ApiKeyPool
from design_hub.infrastructure.providers.apinebula_async import AsyncImageTasksProvider
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
from design_hub.ports.model_provider import AbstractModelProvider
from design_hub.ports.password_cipher import PasswordCipher
from design_hub.ports.text_llm import TextLLMPort
from design_hub.ports.upload_store import UploadStore

# Mock 单价对齐 PRD §3.5 参考价（默认/兜底价；真实单价由 model_config 表热更覆盖，见 WP-H）
_MOCK_UNIT_COSTS: dict[ModelName, Decimal] = {
    ModelName.SEEDREAM_5: Decimal("0.20"),
    ModelName.GPT_IMAGE_2: Decimal("0.05"),
    ModelName.GPT_IMAGE_2_4K: Decimal("0.18"),
    ModelName.WANXIANG_27: Decimal("0.05"),
    ModelName.LINGDONG_2: Decimal("0.04"),
}


def default_model_configs() -> list[ModelConfigRecord]:
    """默认模型配置（启动 seed 用）：单价取 _MOCK_UNIT_COSTS，默认启用。"""
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


def _resolve_image_connection(
    settings: Settings,
    unit_costs: Mapping[ModelName, Decimal] | None,
    default_config: ModelConfigRecord | None,
) -> tuple[str, str, list[str], Decimal]:
    """出图 provider 连接解析（ISSUE-0057）：优先管理员配的默认模型连接（备用渠道切换、治 0056
    单点），需 base_url+model+非空 key（A1 真 key 从 api_key_env 指向的环境变量取）；否则回落 .env。
    单模型口径 MVP：默认模型的连接驱动 GPT_IMAGE_2 出图槽（切默认+重启即换渠道，同 0042 快照口径）。
    """
    if default_config is not None and default_config.base_url and default_config.model:
        keys = [
            k.strip()
            for k in os.environ.get(default_config.api_key_env, "").split(",")
            if k.strip()
        ]
        if keys:
            return (
                default_config.base_url, default_config.model, keys, default_config.unit_cost
            )
    if not settings.gpt_image_base_url or not settings.gpt_image_model:
        raise ValueError("GPT_IMAGE_BASE_URL / GPT_IMAGE_MODEL 未配置（见 .env 或 model_config）")
    keys = [
        k.strip() for k in settings.gpt_image_api_key.get_secret_value().split(",") if k.strip()
    ]
    unit_cost = (unit_costs or {}).get(ModelName.GPT_IMAGE_2, Decimal("0.05"))
    return settings.gpt_image_base_url, settings.gpt_image_model, keys, unit_cost


def build_gpt_image_providers(
    settings: Settings,
    unit_costs: Mapping[ModelName, Decimal] | None = None,
    *,
    default_config: ModelConfigRecord | None = None,
) -> tuple[AbstractModelProvider, AbstractModelProvider]:
    """组装普通异步模型与固定 4K 同步模型，并让两者共享同一 API Key 池。"""
    base_url, model, api_keys, unit_cost = _resolve_image_connection(
        settings, unit_costs, default_config
    )
    image_store = build_image_store(settings)
    key_pool = ApiKeyPool(tuple(api_keys))
    four_k_unit_cost = (unit_costs or {}).get(ModelName.GPT_IMAGE_2_4K, Decimal("0.18"))
    standard = AsyncImageTasksProvider(
        name=ModelName.GPT_IMAGE_2,
        unit_cost=unit_cost,
        base_url=base_url,
        key_pool=key_pool,
        model=model,
        image_store=image_store,
        input_fidelity=settings.gpt_image_input_fidelity,
        trust_env=False,
        poll_interval=settings.gpt_image_async_poll_interval,
        poll_max_elapsed=settings.gpt_image_async_poll_max_elapsed,
        submit_max_retries=settings.gpt_image_max_retries,
        submit_backoff=settings.gpt_image_retry_backoff,
        submit_max_sleep=settings.gpt_image_retry_max_sleep,
    )
    four_k = OpenAICompatImageProvider(
        name=ModelName.GPT_IMAGE_2_4K,
        unit_cost=four_k_unit_cost,
        base_url=base_url,
        key_pool=key_pool,
        model=ModelName.GPT_IMAGE_2_4K.value,
        input_fidelity=settings.gpt_image_input_fidelity,
        response_format=settings.gpt_image_response_format,
        image_store=image_store,
        trust_env=False,
        timeout=settings.gpt_image_4k_timeout,
        max_retries=settings.gpt_image_max_retries,
        retry_backoff=settings.gpt_image_retry_backoff,
        retry_max_sleep=settings.gpt_image_retry_max_sleep,
        retry_max_elapsed=settings.gpt_image_4k_timeout,
        required_size=(3840, 2160),
        required_quality="high",
        required_count=1,
    )
    return standard, four_k


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


def build_password_cipher(settings: Settings) -> PasswordCipher:
    """密码传输加密（ISSUE-0058）：配了 AUTH_RSA_PRIVATE_KEY_PEM → 持久私钥；否则启动生成临时。

    prod/qa 各自 .env 配持久私钥（不入库不入 git）；local/CI 未配则每进程临时密钥对（本机自足）。
    """
    pem = settings.auth_rsa_private_key_pem.get_secret_value()
    if pem:
        return RsaPasswordCipher.from_pem(pem)
    return RsaPasswordCipher.generate()


def build_registry(
    settings: Settings,
    *,
    real_gpt_image: bool = False,
    unit_costs: Mapping[ModelName, Decimal] | None = None,
    default_config: ModelConfigRecord | None = None,
) -> ProviderRegistry:
    """Mock 全模型；real_gpt_image=True 时用真实 Provider 覆盖普通与 4K 模型。

    unit_costs（model_config 真实单价）注入 Provider；default_config（ISSUE-0057 管理员配的
    默认出图模型）驱动真实 provider 的连接（备用渠道切换），缺省回落 .env。按 LSP 覆盖 Mock。
    """
    registry = build_mock_registry(unit_costs)
    if real_gpt_image:
        for provider in build_gpt_image_providers(
            settings, unit_costs, default_config=default_config
        ):
            registry.register(provider)
    return registry
