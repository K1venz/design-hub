import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest

from design_hub.application.admin.model_capability_service import (
    CapabilityTestBusy,
    ModelCapabilityService,
)
from design_hub.domain.enums import ModelType, ProviderType
from design_hub.domain.models import GeneratedImage, ReferenceImage
from design_hub.interface.admin_schemas import (
    ModelCapabilityTestIn,
    ModelCapabilityTestOut,
)
from design_hub.ports.image_store import ImageStore
from design_hub.ports.model_calls import ModelCallContext
from design_hub.ports.model_config_repository import (
    ModelConfigRecord,
    ModelConfigRepository,
)
from design_hub.ports.model_provider import AbstractModelProvider
from design_hub.ports.model_verification import ModelVerificationService
from design_hub.ports.secret_cipher import SecretCipher
from design_hub.ports.text_llm import (
    ChatMessage,
    LLMChunk,
    TextChunk,
    TextLLMPort,
    ToolCall,
    ToolCallChunk,
    ToolSpec,
)


class _Cipher(SecretCipher):
    def public_key_pem(self) -> str:
        return "unused"

    def encrypt(self, plaintext: str) -> str:
        raise AssertionError("capability test only decrypts")

    def decrypt(self, ciphertext_b64: str) -> str:
        return {
            "enc-image": "image-key",
            "enc-existing": "existing-key",
            "enc-chat": "chat-key",
        }[ciphertext_b64]


class _Verifier(ModelVerificationService):
    def __init__(self) -> None:
        self.issued: list[dict[str, Any]] = []

    def issue(
        self,
        *,
        manager_id: str,
        model_id: str,
        model_type: ModelType,
        fingerprint: str,
    ) -> str:
        self.issued.append(
            {
                "manager_id": manager_id,
                "model_id": model_id,
                "model_type": model_type,
                "fingerprint": fingerprint,
            }
        )
        return f"proof:{fingerprint}"

    def verify(
        self,
        proof: str,
        *,
        manager_id: str,
        model_id: str,
        model_type: ModelType,
        fingerprint: str,
    ) -> None:
        raise AssertionError("capability tests issue proofs")


class _Repo(ModelConfigRepository):
    def __init__(self, existing: ModelConfigRecord | None = None) -> None:
        self.existing = existing

    async def list_all(self) -> list[ModelConfigRecord]:
        return [self.existing] if self.existing is not None else []

    async def get(self, name: str) -> ModelConfigRecord | None:
        return (
            self.existing
            if self.existing is not None and self.existing.name == name
            else None
        )

    async def get_default(self, model_type: ModelType) -> str | None:
        return None

    async def create(
        self, *, actor_id: int, record: ModelConfigRecord
    ) -> ModelConfigRecord:
        raise AssertionError("test endpoint must not mutate model config")

    async def update(
        self,
        *,
        actor_id: int,
        record: ModelConfigRecord,
        expected_revision: int,
    ) -> ModelConfigRecord:
        raise AssertionError("test endpoint must not mutate model config")

    async def delete(self, *, actor_id: int, name: str) -> None:
        raise AssertionError("test endpoint must not mutate model config")

    async def set_default(
        self, *, actor_id: int, name: str
    ) -> ModelConfigRecord:
        raise AssertionError("test endpoint must not mutate model config")


class _ImageProvider(AbstractModelProvider):
    name = "probe-image"
    unit_cost = Decimal("0")
    reference_mode = "bytes"

    def __init__(
        self,
        image_store: ImageStore,
        *,
        entered: asyncio.Event | None = None,
        release: asyncio.Event | None = None,
    ) -> None:
        self.image_store = image_store
        self.calls: list[list[ReferenceImage]] = []
        self.entered = entered
        self.release = release

    async def generate(
        self,
        *,
        context: ModelCallContext,
        prompt: str,
        negative_prompt: str,
        reference_images: list[ReferenceImage],
        size: tuple[int, int],
        n: int,
        seed: int | None = None,
        quality: str | None = None,
    ) -> list[GeneratedImage]:
        self.calls.append(reference_images)
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            await self.release.wait()
        stored = await self.image_store.save(b"generated-png")
        return [
            GeneratedImage(
                image_key=stored.key,
                url=stored.url,
                seed=0,
                latency_ms=1,
                cost=Decimal("0"),
            )
        ]


class _ChatProvider(TextLLMPort):
    def complete(
        self,
        *,
        context: ModelCallContext,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
    ) -> AsyncIterator[LLMChunk]:
        async def chunks() -> AsyncIterator[LLMChunk]:
            yield TextChunk("probe ok")
            yield ToolCallChunk(
                (
                    ToolCall(
                        id="probe",
                        name="model_configuration_probe",
                        arguments={"ok": True},
                    ),
                )
            )

        return chunks()


class _Factory:
    def __init__(
        self,
        *,
        entered: asyncio.Event | None = None,
        release: asyncio.Event | None = None,
    ) -> None:
        self.image: _ImageProvider | None = None
        self.entered = entered
        self.release = release

    def build_image(
        self,
        *,
        record: ModelConfigRecord,
        credentials: dict[str, str | tuple[str, ...]],
        image_store: ImageStore,
    ) -> AbstractModelProvider:
        self.image = _ImageProvider(
            image_store,
            entered=self.entered,
            release=self.release,
        )
        return self.image

    def build_text(
        self,
        *,
        record: ModelConfigRecord,
        credentials: dict[str, str | tuple[str, ...]],
    ) -> TextLLMPort:
        return _ChatProvider()


def _service(
    *,
    repo: _Repo | None = None,
    factory: _Factory | None = None,
) -> tuple[ModelCapabilityService, _Verifier, _Factory]:
    verifier = _Verifier()
    provider_factory = factory or _Factory()
    return (
        ModelCapabilityService(
            repository=repo or _Repo(),
            cipher=_Cipher(),
            verifier=verifier,
            providers=provider_factory,
        ),
        verifier,
        provider_factory,
    )


def test_image_probe_generates_then_edits_and_issues_exact_proof(caplog) -> None:
    caplog.set_level(logging.INFO)
    service, verifier, factory = _service()

    result = asyncio.run(
        service.test(
            manager_id="7",
            name="gpt-image-2",
            model_type=ModelType.IMAGE,
            provider_type=ProviderType.OPENAI_COMPAT_IMAGE,
            base_url="https://images.example.test/v1",
            model="upstream-image",
            credentials={"standard_api_keys": ["enc-image"]},
            extra={},
        )
    )

    assert result.checks == ("generate", "edit")
    assert isinstance(result.tested_at, datetime)
    assert result.verification_proof == (
        f"proof:{verifier.issued[0]['fingerprint']}"
    )
    assert factory.image is not None
    assert len(factory.image.calls) == 2
    assert factory.image.calls[0] == []
    assert factory.image.calls[1][0].data is not None
    records = {
        record.msg: record
        for record in caplog.records
        if str(record.msg).startswith("model_capability_test_")
    }
    assert records["model_capability_test_started"].levelno == logging.INFO
    assert records["model_capability_test_started"].chain == "model_configuration"
    assert records["model_capability_test_started"].action == "开始模型连通性测试"
    assert records["model_capability_test_completed"].levelno == logging.INFO
    assert records["model_capability_test_completed"].action == "模型连通性测试成功"


def test_chat_probe_requires_streamed_text_and_named_tool() -> None:
    service, _verifier, _factory = _service()
    result = asyncio.run(
        service.test(
            manager_id="7",
            name="doubao-chat",
            model_type=ModelType.CHAT,
            provider_type=ProviderType.OPENAI_COMPAT_CHAT,
            base_url="https://chat.example.test/v1",
            model="doubao-upstream",
            credentials={"api_key": "enc-chat"},
            extra={"thinking_disabled": True},
        )
    )
    assert result.checks == ("streamed_text", "tool_call")


def test_omitted_credentials_reuse_only_the_named_existing_record() -> None:
    existing = ModelConfigRecord(
        name="existing",
        display_name="Existing",
        model_type=ModelType.IMAGE,
        provider_type=ProviderType.OPENAI_COMPAT_IMAGE,
        base_url="https://old.example.test",
        model="old-upstream",
        credentials_ciphertext={
            "standard_api_keys": ["enc-existing"]
        },
        unit_cost=Decimal("0"),
        enabled=False,
        revision=1,
        verified_at=None,
        verified_fingerprint=None,
        extra={},
    )
    service, _verifier, _factory = _service(repo=_Repo(existing))
    result = asyncio.run(
        service.test(
            manager_id="7",
            name="existing",
            existing_model_name="existing",
            model_type=ModelType.IMAGE,
            provider_type=ProviderType.OPENAI_COMPAT_IMAGE,
            base_url="https://new.example.test",
            model="new-upstream",
            credentials=None,
            extra={},
        )
    )
    assert result.checks == ("generate", "edit")


def test_duplicate_manager_fingerprint_is_rejected_while_active() -> None:
    async def run() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()
        service, _verifier, _factory = _service(
            factory=_Factory(entered=entered, release=release)
        )
        kwargs = {
            "manager_id": "7",
            "name": "gpt-image-2",
            "model_type": ModelType.IMAGE,
            "provider_type": ProviderType.OPENAI_COMPAT_IMAGE,
            "base_url": "https://images.example.test/v1",
            "model": "upstream-image",
            "credentials": {"standard_api_keys": ["enc-image"]},
            "extra": {},
        }
        first = asyncio.create_task(service.test(**kwargs))
        await entered.wait()
        with pytest.raises(CapabilityTestBusy):
            await service.test(**kwargs)
        release.set()
        await first

    asyncio.run(run())


def test_capability_endpoint_schemas_never_return_connection_secrets() -> None:
    request = ModelCapabilityTestIn(
        name="gpt-image-2",
        model_type=ModelType.IMAGE,
        provider_type=ProviderType.OPENAI_COMPAT_IMAGE,
        base_url="https://images.example.test/v1?private=query",
        model="upstream-image",
        credentials={"standard_api_keys": ["ciphertext"]},
        extra={},
    )
    result = ModelCapabilityTestOut(
        verification_proof="proof",
        tested_at=datetime.now().astimezone(),
        checks=["generate", "edit"],
    )
    assert request.existing_model_name is None
    assert result.model_dump() == {
        "verification_proof": "proof",
        "tested_at": result.tested_at,
        "checks": ["generate", "edit"],
    }
