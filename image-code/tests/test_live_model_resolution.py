import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from model_call_fakes import RecordingModelCallRecorder

from design_hub.config.settings import Settings
from design_hub.domain.enums import ModelType, ProviderType
from design_hub.domain.model_config import connection_fingerprint
from design_hub.domain.nano_banana import (
    NANO_BANANA_2_MODEL_ID,
    NANO_BANANA_UPSTREAM_MODEL,
)
from design_hub.domain.tasking import RenderTier
from design_hub.infrastructure.providers.gemini_native import (
    GeminiNativeImageProvider,
)
from design_hub.infrastructure.providers.live_resolution import (
    LiveImageExecutorResolver,
    LiveTextLLMResolver,
)
from design_hub.ports.image_store import ImageStore, StoredImage
from design_hub.ports.model_config_repository import (
    ModelConfigRecord,
    ModelConfigRepository,
)
from design_hub.ports.model_resolution import ModelUnavailableError
from design_hub.ports.secret_cipher import SecretCipher


class _MemoryImageStore(ImageStore):
    async def save(self, data: bytes, *, suffix: str = ".png") -> StoredImage:
        return StoredImage(key=f"probe{suffix}", url=f"/img/probe{suffix}")

    async def load(self, image_key: str) -> bytes:
        raise AssertionError("resolver construction must not load images")


class _Cipher(SecretCipher):
    def __init__(self, plaintext: dict[str, str]) -> None:
        self.plaintext = plaintext

    def public_key_pem(self) -> str:
        return "unused"

    def encrypt(self, plaintext: str) -> str:
        raise AssertionError("runtime resolution only decrypts")

    def decrypt(self, ciphertext_b64: str) -> str:
        return self.plaintext[ciphertext_b64]


class _LeakingCipher(_Cipher):
    def decrypt(self, ciphertext_b64: str) -> str:
        raise ValueError(f"bad ciphertext: {ciphertext_b64}")


class _Repo(ModelConfigRepository):
    def __init__(
        self,
        records: dict[str, ModelConfigRecord],
        *,
        defaults: dict[ModelType, str] | None = None,
    ) -> None:
        self.records = records
        self.defaults = defaults or {}
        self.get_calls: list[str] = []
        self.default_calls: list[ModelType] = []

    async def list_all(self) -> list[ModelConfigRecord]:
        return list(self.records.values())

    async def get(self, name: str) -> ModelConfigRecord | None:
        self.get_calls.append(name)
        return self.records.get(name)

    async def get_default(self, model_type: ModelType) -> str | None:
        self.default_calls.append(model_type)
        return self.defaults.get(model_type)

    async def create(
        self, *, actor_id: int, record: ModelConfigRecord
    ) -> ModelConfigRecord:
        raise AssertionError("runtime resolver is read-only")

    async def update(
        self,
        *,
        actor_id: int,
        record: ModelConfigRecord,
        expected_revision: int,
    ) -> ModelConfigRecord:
        raise AssertionError("runtime resolver is read-only")

    async def delete(self, *, actor_id: int, name: str) -> None:
        raise AssertionError("runtime resolver is read-only")

    async def set_default(
        self, *, actor_id: int, name: str
    ) -> ModelConfigRecord:
        raise AssertionError("runtime resolver is read-only")


def _image_record(
    *,
    revision: int = 1,
    enabled: bool = True,
    verified: bool = True,
    model_type: ModelType = ModelType.IMAGE,
) -> ModelConfigRecord:
    credentials = {
        "standard_api_keys": ("standard-a", "standard-b"),
        "four_k_api_key": "four-k",
    }
    fingerprint = (
        connection_fingerprint(
            model_type=ModelType.IMAGE,
            provider_type=ProviderType.OPENAI_COMPAT_IMAGE,
            base_url="https://images.example.test/v1",
            upstream_model="upstream-image-v2",
            extra={
                "input_fidelity": "high",
                "response_format": "b64_json",
            },
            credentials_plaintext=credentials,
        )
        if model_type is ModelType.IMAGE
        else "0" * 64
    )
    return ModelConfigRecord(
        name="gpt-image-2",
        display_name="GPT Image 2.0",
        model_type=model_type,
        provider_type=ProviderType.OPENAI_COMPAT_IMAGE,
        base_url="https://images.example.test/v1",
        model="upstream-image-v2",
        credentials_ciphertext={
            "standard_api_keys": ["enc-standard-a", "enc-standard-b"],
            "four_k_api_key": "enc-four-k",
        },
        unit_cost=Decimal("0.05"),
        enabled=enabled,
        revision=revision,
        verified_at=datetime.now(UTC) if verified else None,
        verified_fingerprint=fingerprint if verified else None,
        extra={"input_fidelity": "high", "response_format": "b64_json"},
    )


def _chat_record(
    *,
    revision: int = 1,
    enabled: bool = True,
    verified: bool = True,
    model_type: ModelType = ModelType.CHAT,
    name: str = "doubao-chat",
) -> ModelConfigRecord:
    fingerprint = connection_fingerprint(
        model_type=model_type,
        provider_type=ProviderType.OPENAI_COMPAT_CHAT,
        base_url="https://chat.example.test/v1",
        upstream_model="doubao-upstream",
        extra={"thinking_disabled": True},
        credentials_plaintext={"api_key": "chat-key"},
    )
    return ModelConfigRecord(
        name=name,
        display_name="Doubao Chat",
        model_type=model_type,
        provider_type=ProviderType.OPENAI_COMPAT_CHAT,
        base_url="https://chat.example.test/v1",
        model="doubao-upstream",
        credentials_ciphertext={"api_key": "enc-chat"},
        unit_cost=Decimal("0"),
        enabled=enabled,
        revision=revision,
        verified_at=datetime.now(UTC) if verified else None,
        verified_fingerprint=fingerprint if verified else None,
        extra={"thinking_disabled": True},
    )


def _wan_record() -> ModelConfigRecord:
    fingerprint = connection_fingerprint(
        model_type=ModelType.IMAGE,
        provider_type=ProviderType.DASHSCOPE_WAN_IMAGE,
        base_url="https://dashscope.example.test",
        upstream_model="wan2.7-image-pro",
        extra={"watermark": False},
        credentials_plaintext={"api_key": "wan-key"},
    )
    return ModelConfigRecord(
        name="wan2.7-image-pro",
        display_name="Wan 2.7 Image Pro",
        model_type=ModelType.IMAGE,
        provider_type=ProviderType.DASHSCOPE_WAN_IMAGE,
        base_url="https://dashscope.example.test",
        model="wan2.7-image-pro",
        credentials_ciphertext={"api_key": "enc-wan"},
        unit_cost=Decimal("0.50"),
        enabled=True,
        revision=1,
        verified_at=datetime.now(UTC),
        verified_fingerprint=fingerprint,
        extra={"watermark": False},
    )


def _nano_record() -> ModelConfigRecord:
    credentials = {"api_keys": ("nano-a", "nano-b")}
    fingerprint = connection_fingerprint(
        model_type=ModelType.IMAGE,
        provider_type=ProviderType.GEMINI_NATIVE_IMAGE,
        base_url="https://gemini.example.test",
        upstream_model=NANO_BANANA_UPSTREAM_MODEL,
        extra={},
        credentials_plaintext=credentials,
    )
    return ModelConfigRecord(
        name=NANO_BANANA_2_MODEL_ID,
        display_name="Nano Banana 2",
        model_type=ModelType.IMAGE,
        provider_type=ProviderType.GEMINI_NATIVE_IMAGE,
        base_url="https://gemini.example.test",
        model=NANO_BANANA_UPSTREAM_MODEL,
        credentials_ciphertext={"api_keys": ["enc-nano-a", "enc-nano-b"]},
        unit_cost=Decimal("0.10"),
        enabled=True,
        revision=1,
        verified_at=datetime.now(UTC),
        verified_fingerprint=fingerprint,
        extra={},
    )
def _image_resolver(
    repo: _Repo,
    *,
    cipher: SecretCipher | None = None,
) -> LiveImageExecutorResolver:
    return LiveImageExecutorResolver(
        repository=repo,
        cipher=cipher
        or _Cipher(
            {
                "enc-standard-a": "standard-a",
                "enc-standard-b": "standard-b",
                "enc-four-k": "four-k",
            }
        ),
        recorder=RecordingModelCallRecorder(),
        image_store=_MemoryImageStore(),
        settings=Settings(),
    )


def test_image_resolver_queries_every_call_and_caches_exact_revision_and_tier() -> None:
    async def run() -> None:
        record = _image_record()
        repo = _Repo({record.name: record})
        resolver = _image_resolver(repo)

        standard_1 = await resolver.resolve(record.name, RenderTier.STANDARD)
        standard_2 = await resolver.resolve(record.name, RenderTier.STANDARD)
        four_k = await resolver.resolve(record.name, RenderTier.FOUR_K)

        assert repo.get_calls == [record.name, record.name, record.name]
        assert standard_1 is standard_2
        assert standard_1 is not four_k
        assert standard_1.provider.name == record.name
        assert standard_1.provider._model == "gpt-image-2"
        assert standard_1.provider._key_pool.key_for(0, 0) == "standard-a"
        assert four_k.provider.name == record.name
        assert four_k.provider._model == "gpt-image-2-4k"
        assert four_k.provider._key_pool.key_for(0, 0) == "four-k"
        assert four_k.provider._api_contract is not None
        assert four_k.provider._api_contract.required_quality == "high"
        assert four_k.provider._api_contract.provider_max_count == 10

        repo.records[record.name] = replace(record, revision=2)
        revised = await resolver.resolve(record.name, RenderTier.STANDARD)
        assert revised is not standard_1

    asyncio.run(run())


@pytest.mark.parametrize(
    "record",
    [
        _image_record(enabled=False),
        _image_record(verified=False),
        _image_record(model_type=ModelType.CHAT),
    ],
)
def test_image_resolver_rejects_unavailable_rows(record: ModelConfigRecord) -> None:
    with pytest.raises(ModelUnavailableError, match="model unavailable"):
        asyncio.run(_image_resolver(_Repo({record.name: record})).resolve(
            record.name, RenderTier.STANDARD
        ))


def test_image_resolver_rejects_missing_rows() -> None:
    with pytest.raises(ModelUnavailableError, match="model unavailable"):
        asyncio.run(
            _image_resolver(_Repo({})).resolve(
                "missing-image", RenderTier.STANDARD
            )
        )


def test_resolution_sanitizes_secret_decryption_errors() -> None:
    ciphertext = "ciphertext-must-never-leak"
    record = replace(
        _image_record(),
        credentials_ciphertext={
            "standard_api_keys": [ciphertext],
            "four_k_api_key": ciphertext,
        },
    )
    with pytest.raises(ModelUnavailableError) as caught:
        asyncio.run(
            _image_resolver(
                _Repo({record.name: record}),
                cipher=_LeakingCipher({}),
            ).resolve(record.name, RenderTier.STANDARD)
        )
    assert ciphertext not in str(caught.value)
    assert ciphertext not in repr(caught.value.__cause__)


def test_text_resolver_reads_default_and_row_on_every_operation() -> None:
    async def run() -> None:
        record = _chat_record()
        repo = _Repo(
            {record.name: record},
            defaults={ModelType.CHAT: record.name},
        )
        resolver = LiveTextLLMResolver(
            repository=repo,
            cipher=_Cipher({"enc-chat": "chat-key"}),
            recorder=RecordingModelCallRecorder(),
            settings=Settings(),
        )

        first = await resolver.resolve_default(ModelType.CHAT)
        second = await resolver.resolve_default(ModelType.CHAT)

        assert first is second
        assert repo.default_calls == [ModelType.CHAT, ModelType.CHAT]
        assert repo.get_calls == [record.name, record.name]
        assert first.name == record.name
        assert first._model == "doubao-upstream"
        assert first._extra_body == {"thinking": {"type": "disabled"}}

    asyncio.run(run())


def test_text_resolver_resolves_explicit_model_without_reading_default() -> None:
    async def run() -> None:
        record = _chat_record()
        repo = _Repo({record.name: record})
        resolver = LiveTextLLMResolver(
            repository=repo,
            cipher=_Cipher({"enc-chat": "chat-key"}),
            recorder=RecordingModelCallRecorder(),
            settings=Settings(),
        )

        first = await resolver.resolve(record.name, ModelType.CHAT)
        second = await resolver.resolve(record.name, ModelType.CHAT)

        assert first is second
        assert repo.default_calls == []
        assert repo.get_calls == [record.name, record.name]

    asyncio.run(run())


@pytest.mark.parametrize(
    "record",
    [None, _chat_record(enabled=False), _chat_record(verified=False)],
)
def test_text_resolver_rejects_unavailable_explicit_model(
    record: ModelConfigRecord | None,
) -> None:
    records = {} if record is None else {record.name: record}
    with pytest.raises(ModelUnavailableError, match="model unavailable"):
        asyncio.run(
            LiveTextLLMResolver(
                repository=_Repo(records),
                cipher=_Cipher({"enc-chat": "chat-key"}),
                recorder=RecordingModelCallRecorder(),
                settings=Settings(),
            ).resolve("doubao-chat", ModelType.CHAT)
        )


def test_text_resolver_scopes_default_and_explicit_resolution_by_model_type() -> None:
    async def run() -> None:
        record = _chat_record(
            model_type=ModelType.VISION,
            name="doubao-vision",
        )
        repo = _Repo(
            {record.name: record},
            defaults={ModelType.VISION: record.name},
        )
        resolver = LiveTextLLMResolver(
            repository=repo,
            cipher=_Cipher({"enc-chat": "chat-key"}),
            recorder=RecordingModelCallRecorder(),
            settings=Settings(),
        )

        resolved = await resolver.resolve_default(ModelType.VISION)

        assert resolved.name == record.name
        assert repo.default_calls == [ModelType.VISION]
        with pytest.raises(ModelUnavailableError, match="model unavailable"):
            await resolver.resolve(record.name, ModelType.CHAT)

    asyncio.run(run())


def test_image_resolver_constructs_recoverable_wan_for_every_supported_tier() -> None:
    async def run() -> None:
        record = _wan_record()
        resolver = _image_resolver(
            _Repo({record.name: record}),
            cipher=_Cipher({"enc-wan": "wan-key"}),
        )

        for tier in (
            RenderTier.STANDARD,
            RenderTier.TWO_K,
            RenderTier.FOUR_K,
        ):
            executor = await resolver.resolve(record.name, tier)
            assert executor.provider.name == record.name
            assert executor.reference_mode == "url"

    asyncio.run(run())


def test_image_resolver_constructs_nano_banana_for_every_supported_tier() -> None:
    async def run() -> None:
        record = _nano_record()
        resolver = _image_resolver(
            _Repo({record.name: record}),
            cipher=_Cipher(
                {"enc-nano-a": "nano-a", "enc-nano-b": "nano-b"}
            ),
        )

        for tier in (
            RenderTier.STANDARD,
            RenderTier.TWO_K,
            RenderTier.FOUR_K,
        ):
            executor = await resolver.resolve(record.name, tier)
            assert isinstance(executor.provider, GeminiNativeImageProvider)
            assert executor.reference_mode == "bytes"
            assert executor.provider._model == NANO_BANANA_UPSTREAM_MODEL
            assert executor.provider._key_pool.key_for(0, 0) == "nano-a"

    asyncio.run(run())
