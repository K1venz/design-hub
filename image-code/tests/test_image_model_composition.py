"""真实图像模型的双 Provider 装配契约。"""

from decimal import Decimal

from design_hub.composition import build_registry, default_model_configs
from design_hub.config.settings import Settings
from design_hub.domain.enums import ModelName
from design_hub.infrastructure.providers.apinebula_async import AsyncImageTasksProvider
from design_hub.infrastructure.providers.openai_compat import OpenAICompatImageProvider


def test_real_registry_registers_standard_and_fixed_4k_models_with_one_key_pool() -> None:
    settings = Settings(
        gpt_image_base_url="https://images.example.invalid/v1",
        gpt_image_api_key="test-key-a,test-key-b",
        gpt_image_model="standard-upstream-model",
    )

    registry = build_registry(settings, real_gpt_image=True)

    standard = registry.get(ModelName.GPT_IMAGE_2)
    four_k = registry.get(ModelName.GPT_IMAGE_2_4K)
    defaults = {record.name: record for record in default_model_configs()}

    assert ModelName.GPT_IMAGE_2_4K.value == "gpt-image-2-4k"
    assert defaults["gpt-image-2"].unit_cost == Decimal("0.05")
    assert defaults["gpt-image-2-4k"].unit_cost == Decimal("0.18")
    assert isinstance(standard, AsyncImageTasksProvider)
    assert isinstance(four_k, OpenAICompatImageProvider)
    assert standard.reference_mode == "url"
    assert four_k.reference_mode == "bytes"
    assert standard._key_pool is four_k._key_pool
    assert four_k._model == "gpt-image-2-4k"
    assert four_k._timeout == 1800.0
    assert four_k._retry_max_elapsed == 1800.0
