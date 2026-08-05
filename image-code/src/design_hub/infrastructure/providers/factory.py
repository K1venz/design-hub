from collections.abc import Mapping

from design_hub.config.settings import Settings
from design_hub.domain.enums import ProviderType
from design_hub.domain.gpt_image_2 import (
    GPT_IMAGE_2_MODEL_ID,
    gpt_image_2_contract,
)
from design_hub.domain.model_config import CredentialValue
from design_hub.domain.tasking import RenderTier
from design_hub.infrastructure.providers.api_key_pool import ApiKeyPool
from design_hub.infrastructure.providers.dashscope_wan import (
    DashScopeWanImageProvider,
)
from design_hub.infrastructure.providers.openai_compat import (
    OpenAICompatImageProvider,
)
from design_hub.infrastructure.providers.openai_compat_text import (
    OpenAICompatTextProvider,
)
from design_hub.ports.image_store import ImageStore
from design_hub.ports.model_calls import ModelCallRecorder
from design_hub.ports.model_config_repository import ModelConfigRecord
from design_hub.ports.model_provider import AbstractModelProvider
from design_hub.ports.text_llm import TextLLMPort


def build_image_provider(
    *,
    record: ModelConfigRecord,
    credentials: Mapping[str, CredentialValue],
    render_tier: RenderTier,
    recorder: ModelCallRecorder,
    image_store: ImageStore,
    settings: Settings,
) -> AbstractModelProvider:
    if record.provider_type is ProviderType.DASHSCOPE_WAN_IMAGE:
        if render_tier is RenderTier.FOUR_K:
            raise ValueError("Wan does not support the 4K render tier")
        watermark = record.extra.get("watermark", False)
        if type(watermark) is not bool:
            raise ValueError("invalid Wan provider options")
        return DashScopeWanImageProvider(
            name=record.name,
            unit_cost=record.unit_cost,
            base_url=record.base_url,
            api_key=_required_secret(credentials, "api_key"),
            model=record.model,
            image_store=image_store,
            recorder=recorder,
            watermark=watermark,
            request_timeout=settings.wan_request_timeout,
            trust_env=False,
            poll_interval=settings.wan_poll_interval,
            poll_max_elapsed=settings.wan_poll_max_elapsed,
            retry_count=settings.wan_retry_count,
            retry_backoff=settings.wan_retry_backoff,
            max_download_bytes=settings.wan_max_download_bytes,
        )
    if record.provider_type is not ProviderType.OPENAI_COMPAT_IMAGE:
        raise ValueError("unsupported image provider")

    if record.name != GPT_IMAGE_2_MODEL_ID:
        raise ValueError("OpenAI-compatible image model has no API contract")
    api_contract = gpt_image_2_contract(render_tier)

    if render_tier is RenderTier.FOUR_K:
        key_pool = ApiKeyPool((_required_secret(credentials, "four_k_api_key"),))
        timeout = settings.gpt_image_4k_timeout
        retry_max_elapsed = settings.gpt_image_4k_timeout
    else:
        key_pool = ApiKeyPool(
            _required_secret_tuple(credentials, "standard_api_keys")
        )
        timeout = settings.gpt_image_request_timeout
        retry_max_elapsed = settings.gpt_image_retry_max_elapsed

    return OpenAICompatImageProvider(
        name=record.name,
        unit_cost=record.unit_cost,
        base_url=record.base_url,
        key_pool=key_pool,
        model=api_contract.upstream_model,
        recorder=recorder,
        input_fidelity=_optional_string(record.extra, "input_fidelity"),
        response_format=_optional_string(record.extra, "response_format"),
        image_store=image_store,
        trust_env=False,
        timeout=timeout,
        max_retries=settings.gpt_image_max_retries,
        retry_backoff=settings.gpt_image_retry_backoff,
        retry_max_sleep=settings.gpt_image_retry_max_sleep,
        retry_max_elapsed=retry_max_elapsed,
    )


def build_text_provider(
    *,
    record: ModelConfigRecord,
    credentials: Mapping[str, CredentialValue],
    recorder: ModelCallRecorder,
    settings: Settings,
) -> TextLLMPort:
    if record.provider_type is not ProviderType.OPENAI_COMPAT_CHAT:
        raise ValueError("unsupported chat provider")
    thinking_disabled = record.extra.get("thinking_disabled", False)
    if type(thinking_disabled) is not bool:
        raise ValueError("invalid chat provider options")
    return OpenAICompatTextProvider(
        name=record.name,
        base_url=record.base_url,
        api_key=_required_secret(credentials, "api_key"),
        model=record.model,
        recorder=recorder,
        timeout=settings.text_llm_request_timeout,
        trust_env=False,
        extra_body=(
            {"thinking": {"type": "disabled"}}
            if thinking_disabled
            else {}
        ),
    )


def _required_secret(
    credentials: Mapping[str, CredentialValue], field: str
) -> str:
    value = credentials.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError("invalid decrypted credentials")
    return value


def _required_secret_tuple(
    credentials: Mapping[str, CredentialValue], field: str
) -> tuple[str, ...]:
    value = credentials.get(field)
    if (
        not isinstance(value, tuple)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise ValueError("invalid decrypted credentials")
    return value


def _optional_string(extra: Mapping[str, object], field: str) -> str:
    value = extra.get(field, "")
    if not isinstance(value, str):
        raise ValueError("invalid provider options")
    return value
