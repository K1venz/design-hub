"""真实图像模型的双 Provider 装配契约。"""

from decimal import Decimal

import pytest
from model_call_fakes import RecordingModelCallRecorder

from design_hub.composition import (
    build_gpt_image_providers,
    build_mock_registry,
    build_registry,
    default_model_configs,
)
from design_hub.config.settings import Settings
from design_hub.infrastructure.providers.openai_compat import OpenAICompatImageProvider
from design_hub.ports.model_config_repository import ModelConfigRecord


def _settings(*, four_k_key: str = "test-key-4k") -> Settings:
    return Settings(
        gpt_image_base_url="https://images.example.invalid/v1",
        gpt_image_api_key="test-key-a,test-key-b",
        gpt_image_4k_api_key=four_k_key,
        gpt_image_model="standard-upstream-model",
    )


def test_real_registry_uses_independent_key_pools_for_standard_and_4k() -> None:
    registry = build_registry(
        _settings(),
        recorder=RecordingModelCallRecorder(),
        real_gpt_image=True,
        unit_costs={
            "gpt-image-2": Decimal("0.40"),
            "gpt-image-2-4k": Decimal("9.99"),
        },
    )

    standard = registry.get("gpt-image-2")
    four_k = registry.get("gpt-image-2-4k")
    defaults = {record.name: record for record in default_model_configs()}

    assert defaults["gpt-image-2"].unit_cost == Decimal("0.05")
    assert "gpt-image-2-4k" not in defaults
    assert isinstance(standard, OpenAICompatImageProvider)
    assert isinstance(four_k, OpenAICompatImageProvider)
    assert standard.reference_mode == "bytes"
    assert four_k.reference_mode == "bytes"
    assert standard._key_pool is not four_k._key_pool
    assert standard._key_pool.key_for(0, 0) == "test-key-a"
    assert standard._key_pool.key_for(0, 1) == "test-key-b"
    assert four_k._key_pool.key_for(0, 0) == "test-key-4k"
    assert four_k._key_pool.key_for(0, 1) == "test-key-4k"
    assert standard.unit_cost == Decimal("0.05")
    assert four_k.unit_cost == Decimal("0.18")
    assert standard._model == "standard-upstream-model"
    assert four_k._model == "gpt-image-2-4k"
    assert four_k._operation_timeout == 1800.0
    assert four_k._retry_max_elapsed == 1800.0


def test_real_registry_requires_one_4k_key() -> None:
    with pytest.raises(ValueError, match="GPT_IMAGE_4K_API_KEY.*exactly one"):
        build_gpt_image_providers(
            _settings(four_k_key=""),
            RecordingModelCallRecorder(),
        )


def test_real_registry_rejects_multiple_4k_keys() -> None:
    with pytest.raises(ValueError, match="GPT_IMAGE_4K_API_KEY.*exactly one"):
        build_gpt_image_providers(
            _settings(four_k_key="test-key-4k-a,test-key-4k-b"),
            RecordingModelCallRecorder(),
        )


@pytest.mark.parametrize(
    "standard_keys",
    ["test-key-a", "test-key-a,test-key-b,test-key-c"],
)
def test_real_registry_requires_exactly_two_standard_keys(standard_keys: str) -> None:
    settings = _settings()
    settings.gpt_image_api_key = settings.gpt_image_api_key.__class__(standard_keys)

    with pytest.raises(ValueError, match="GPT_IMAGE_API_KEY.*exactly two"):
        build_gpt_image_providers(settings, RecordingModelCallRecorder())


def test_compatible_default_connection_cannot_override_fixed_runtime_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMPAT_IMAGE_KEYS", "test-key-a,test-key-b")
    configured = ModelConfigRecord(
        name="configured-image-route",
        unit_cost=Decimal("0.40"),
        enabled=True,
        extra={},
        provider_type="openai_compat_image",
        base_url="https://configured.example.invalid/v1",
        model="configured-upstream-model",
        api_key_env="COMPAT_IMAGE_KEYS",
        is_default=True,
    )

    standard, four_k = build_gpt_image_providers(
        _settings(),
        RecordingModelCallRecorder(),
        unit_costs={"gpt-image-2": Decimal("0.40")},
        default_config=configured,
    )

    assert standard.unit_cost == Decimal("0.05")
    assert four_k.unit_cost == Decimal("0.18")


def test_mock_runtime_also_ignores_stale_fixed_model_prices() -> None:
    registry = build_mock_registry(
        {
            "gpt-image-2": Decimal("0.40"),
            "gpt-image-2-4k": Decimal("9.99"),
        }
    )

    assert registry.get("gpt-image-2").unit_cost == Decimal("0.05")
    assert registry.get("gpt-image-2-4k").unit_cost == Decimal("0.18")


def test_incompatible_default_connection_protocol_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASYNC_IMAGE_KEYS", "test-key-a")
    incompatible = ModelConfigRecord(
        name="legacy-async-route",
        unit_cost=Decimal("0.40"),
        enabled=True,
        extra={},
        provider_type="apinebula_async_image",
        base_url="https://configured.example.invalid/v1",
        model="gpt-image-2",
        api_key_env="ASYNC_IMAGE_KEYS",
        is_default=True,
    )

    with pytest.raises(ValueError, match="openai_compat_image"):
        build_gpt_image_providers(
            _settings(),
            RecordingModelCallRecorder(),
            default_config=incompatible,
        )
