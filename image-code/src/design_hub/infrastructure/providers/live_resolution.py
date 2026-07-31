from __future__ import annotations

from design_hub.config.settings import Settings
from design_hub.domain.enums import ModelType
from design_hub.domain.model_config import (
    CredentialValue,
    connection_fingerprint,
)
from design_hub.domain.tasking import RenderTier
from design_hub.infrastructure.providers.execution import (
    ProviderExecutionAdapter,
)
from design_hub.infrastructure.providers.factory import (
    build_image_provider,
    build_text_provider,
)
from design_hub.ports.image_store import ImageStore
from design_hub.ports.model_calls import ModelCallRecorder
from design_hub.ports.model_config_repository import (
    ModelConfigRecord,
    ModelConfigRepository,
)
from design_hub.ports.model_resolution import ModelUnavailableError
from design_hub.ports.provider_execution import ProviderExecutor
from design_hub.ports.secret_cipher import SecretCipher
from design_hub.ports.text_llm import TextLLMPort

_UNAVAILABLE = "model unavailable"


class LiveImageExecutorResolver:
    def __init__(
        self,
        *,
        repository: ModelConfigRepository,
        cipher: SecretCipher,
        recorder: ModelCallRecorder,
        image_store: ImageStore,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._cipher = cipher
        self._recorder = recorder
        self._image_store = image_store
        self._settings = settings
        self._cache: dict[
            tuple[str, int, RenderTier], ProviderExecutor
        ] = {}

    async def resolve(
        self, model_id: str, render_tier: RenderTier
    ) -> ProviderExecutor:
        record = await self._repository.get(_required_model_id(model_id))
        credentials = _require_record(
            record,
            expected_type=ModelType.IMAGE,
            cipher=self._cipher,
        )
        assert record is not None
        key = (record.name, record.revision, render_tier)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        try:
            provider = build_image_provider(
                record=record,
                credentials=credentials,
                render_tier=render_tier,
                recorder=self._recorder,
                image_store=self._image_store,
                settings=self._settings,
            )
        except (KeyError, TypeError, ValueError):
            raise ModelUnavailableError(_UNAVAILABLE) from None
        executor = ProviderExecutionAdapter(provider)
        self._cache[key] = executor
        return executor


class LiveTextLLMResolver:
    def __init__(
        self,
        *,
        repository: ModelConfigRepository,
        cipher: SecretCipher,
        recorder: ModelCallRecorder,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._cipher = cipher
        self._recorder = recorder
        self._settings = settings
        self._cache: dict[tuple[str, int], TextLLMPort] = {}

    async def resolve_default(self) -> TextLLMPort:
        default_name = await self._repository.get_default(ModelType.CHAT)
        if default_name is None:
            raise ModelUnavailableError(_UNAVAILABLE)
        return await self.resolve(default_name)

    async def resolve(self, model_id: str) -> TextLLMPort:
        record = await self._repository.get(_required_model_id(model_id))
        credentials = _require_record(
            record,
            expected_type=ModelType.CHAT,
            cipher=self._cipher,
        )
        assert record is not None
        key = (record.name, record.revision)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        try:
            provider = build_text_provider(
                record=record,
                credentials=credentials,
                recorder=self._recorder,
                settings=self._settings,
            )
        except (KeyError, TypeError, ValueError):
            raise ModelUnavailableError(_UNAVAILABLE) from None
        self._cache[key] = provider
        return provider


def _required_model_id(model_id: str) -> str:
    if not isinstance(model_id, str) or not model_id.strip():
        raise ModelUnavailableError(_UNAVAILABLE)
    return model_id.strip()


def _require_record(
    record: ModelConfigRecord | None,
    *,
    expected_type: ModelType,
    cipher: SecretCipher,
) -> dict[str, CredentialValue]:
    if (
        record is None
        or record.model_type is not expected_type
        or not record.enabled
        or record.verified_at is None
        or record.verified_fingerprint is None
    ):
        raise ModelUnavailableError(_UNAVAILABLE)
    credentials = _decrypt_credentials(
        cipher, record.credentials_ciphertext
    )
    try:
        fingerprint = connection_fingerprint(
            model_type=record.model_type,
            provider_type=record.provider_type,
            base_url=record.base_url,
            upstream_model=record.model,
            extra=record.extra,
            credentials_plaintext=credentials,
        )
    except (KeyError, TypeError, ValueError):
        raise ModelUnavailableError(_UNAVAILABLE) from None
    if fingerprint != record.verified_fingerprint:
        raise ModelUnavailableError(_UNAVAILABLE)
    return credentials


def _decrypt_credentials(
    cipher: SecretCipher,
    encrypted: dict[str, str | list[str]],
) -> dict[str, CredentialValue]:
    try:
        decrypted: dict[str, CredentialValue] = {}
        for field, value in encrypted.items():
            if isinstance(value, list):
                decrypted[field] = tuple(
                    cipher.decrypt(item) for item in value
                )
            else:
                decrypted[field] = cipher.decrypt(value)
        return decrypted
    except (KeyError, TypeError, ValueError):
        raise ModelUnavailableError(_UNAVAILABLE) from None
