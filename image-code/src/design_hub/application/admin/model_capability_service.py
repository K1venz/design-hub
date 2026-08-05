import asyncio
import base64
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from typing import Protocol

from PIL import Image

from design_hub.application.admin.model_config_service import (
    CiphertextCredentials,
    _decrypt_credentials,
    _fingerprint,
    _normalize_base_url,
    _normalize_required_text,
    _validate_ciphertext_credentials,
)
from design_hub.config.settings import Settings
from design_hub.domain.admin import ModelOperation
from design_hub.domain.enums import ModelType, ProviderType
from design_hub.domain.image_capabilities import ImageOutputSpec
from design_hub.domain.models import GeneratedImage, ReferenceImage
from design_hub.domain.tasking import RenderTier
from design_hub.infrastructure.providers.factory import (
    build_image_provider,
    build_text_provider,
)
from design_hub.ports.image_store import ImageStore, StoredImage
from design_hub.ports.model_calls import (
    ModelCallContext,
    ModelCallRecorder,
)
from design_hub.ports.model_config_repository import (
    ModelConfigRecord,
    ModelConfigRepository,
)
from design_hub.ports.model_provider import AbstractModelProvider
from design_hub.ports.model_verification import ModelVerificationService
from design_hub.ports.secret_cipher import SecretCipher
from design_hub.ports.text_llm import (
    ChatMessage,
    TextChunk,
    TextLLMPort,
    ToolCallChunk,
    ToolSpec,
)

_PROBE_TOOL = "model_configuration_probe"
_PROBE_PROMPT = "Create a neutral studio product image for connection testing."
logger = logging.getLogger(__name__)


class CapabilityTestBusy(ValueError):
    pass


class CapabilityTestFailed(ValueError):
    def __init__(self, *, protocol: str, check: str) -> None:
        super().__init__(
            f"capability test failed: protocol={protocol}, check={check}"
        )


@dataclass(frozen=True)
class CapabilityTestResult:
    verification_proof: str
    tested_at: datetime
    checks: tuple[str, ...]


class CapabilityProviderFactory(Protocol):
    def build_image(
        self,
        *,
        record: ModelConfigRecord,
        credentials: dict[str, str | tuple[str, ...]],
        image_store: ImageStore,
    ) -> AbstractModelProvider: ...

    def build_text(
        self,
        *,
        record: ModelConfigRecord,
        credentials: dict[str, str | tuple[str, ...]],
    ) -> TextLLMPort: ...


@dataclass(frozen=True)
class LiveCapabilityProviderFactory:
    recorder: ModelCallRecorder
    settings: Settings

    def build_image(
        self,
        *,
        record: ModelConfigRecord,
        credentials: dict[str, str | tuple[str, ...]],
        image_store: ImageStore,
    ) -> AbstractModelProvider:
        from design_hub.domain.tasking import RenderTier

        return build_image_provider(
            record=record,
            credentials=credentials,
            render_tier=RenderTier.STANDARD,
            recorder=self.recorder,
            image_store=image_store,
            settings=self.settings,
        )

    def build_text(
        self,
        *,
        record: ModelConfigRecord,
        credentials: dict[str, str | tuple[str, ...]],
    ) -> TextLLMPort:
        return build_text_provider(
            record=record,
            credentials=credentials,
            recorder=self.recorder,
            settings=self.settings,
        )


@dataclass
class ModelCapabilityService:
    repository: ModelConfigRepository
    cipher: SecretCipher
    verifier: ModelVerificationService
    providers: CapabilityProviderFactory
    _active: set[tuple[str, str]] = field(default_factory=set)
    _active_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def test(
        self,
        *,
        manager_id: str,
        name: str,
        model_type: ModelType,
        provider_type: ProviderType,
        base_url: str,
        model: str,
        credentials: CiphertextCredentials | None,
        extra: Mapping[str, object],
        existing_model_name: str | None = None,
    ) -> CapabilityTestResult:
        try:
            normalized_name = _normalize_required_text(name)
            normalized_base_url = _normalize_base_url(base_url)
            normalized_model = _normalize_required_text(model)
            encrypted = await self._credentials_for_test(
                provider_type=provider_type,
                credentials=credentials,
                existing_model_name=existing_model_name,
            )
            try:
                plaintext = _decrypt_credentials(self.cipher, encrypted)
                fingerprint = _fingerprint(
                    model_type=model_type,
                    provider_type=provider_type,
                    base_url=normalized_base_url,
                    model=normalized_model,
                    extra=extra,
                    credentials=plaintext,
                )
            except (KeyError, TypeError, ValueError):
                raise ValueError(
                    "invalid capability test configuration"
                ) from None
        except (KeyError, TypeError, ValueError):
            logger.warning(
                "model_capability_test_rejected",
                extra={
                    "chain": "model_configuration",
                    "action": "模型配置未通过业务校验",
                    "model": name,
                    "status": "rejected",
                },
            )
            raise

        active_key = (manager_id, fingerprint)
        async with self._active_lock:
            if active_key in self._active:
                logger.warning(
                    "model_capability_test_rejected",
                    extra={
                        "chain": "model_configuration",
                        "action": "模型配置未通过业务校验",
                        "model": normalized_name,
                        "status": "busy",
                    },
                )
                raise CapabilityTestBusy(
                    "an identical capability test is already running"
                )
            self._active.add(active_key)
        try:
            logger.info(
                "model_capability_test_started",
                extra={
                    "chain": "model_configuration",
                    "action": "开始模型连通性测试",
                    "model": normalized_name,
                    "status": "started",
                },
            )
            record = ModelConfigRecord(
                name=normalized_name,
                display_name=normalized_name,
                model_type=model_type,
                provider_type=provider_type,
                base_url=normalized_base_url,
                model=normalized_model,
                credentials_ciphertext=encrypted,
                unit_cost=Decimal("0"),
                enabled=False,
                revision=0,
                verified_at=None,
                verified_fingerprint=None,
                extra=dict(extra),
            )
            checks = (
                await self._probe_image(record, plaintext, manager_id)
                if model_type is ModelType.IMAGE
                else await self._probe_chat(
                    record, plaintext, manager_id
                )
            )
            tested_at = datetime.now(UTC)
            proof = self.verifier.issue(
                manager_id=manager_id,
                model_id=normalized_name,
                model_type=model_type,
                fingerprint=fingerprint,
            )
            logger.info(
                "model_capability_test_completed",
                extra={
                    "chain": "model_configuration",
                    "action": "模型连通性测试成功",
                    "model": normalized_name,
                    "status": "completed",
                },
            )
            return CapabilityTestResult(
                verification_proof=proof,
                tested_at=tested_at,
                checks=checks,
            )
        except Exception:
            logger.error(
                "model_capability_test_failed",
                extra={
                    "chain": "model_configuration",
                    "action": "模型连通性测试发生系统错误",
                    "model": normalized_name,
                    "status": "failed",
                },
                exc_info=True,
            )
            raise
        finally:
            async with self._active_lock:
                self._active.remove(active_key)

    async def _credentials_for_test(
        self,
        *,
        provider_type: ProviderType,
        credentials: CiphertextCredentials | None,
        existing_model_name: str | None,
    ) -> CiphertextCredentials:
        if credentials is not None:
            return _validate_ciphertext_credentials(
                provider_type, credentials
            )
        if existing_model_name is None:
            raise ValueError("credentials are required")
        existing = await self.repository.get(
            _normalize_required_text(existing_model_name)
        )
        if existing is None:
            raise ValueError("existing model configuration not found")
        return _validate_ciphertext_credentials(
            provider_type,
            existing.credentials_ciphertext,
        )

    async def _probe_image(
        self,
        record: ModelConfigRecord,
        credentials: dict[str, str | tuple[str, ...]],
        manager_id: str,
    ) -> tuple[str, ...]:
        store = _ProbeImageStore()
        try:
            provider = self.providers.build_image(
                record=record,
                credentials=credentials,
                image_store=store,
            )
        except Exception:
            raise CapabilityTestFailed(
                protocol=record.provider_type.value,
                check="construct",
            ) from None
        generated = await self._generate_probe(
            provider,
            context=ModelCallContext(
                user_id=manager_id,
                operation=ModelOperation.IMAGE_GENERATION,
            ),
            references=[],
            check="generate",
        )
        if generated.image_key not in store.images:
            raise CapabilityTestFailed(
                protocol=record.provider_type.value,
                check="generate_store",
            )
        probe_png = _deterministic_png()
        reference = (
            ReferenceImage(data=probe_png)
            if provider.reference_mode == "bytes"
            else ReferenceImage(url=_data_url(probe_png))
        )
        edited = await self._generate_probe(
            provider,
            context=ModelCallContext(
                user_id=manager_id,
                operation=ModelOperation.IMAGE_EDIT,
            ),
            references=[reference],
            check="edit",
        )
        if edited.image_key not in store.images:
            raise CapabilityTestFailed(
                protocol=record.provider_type.value,
                check="edit_store",
            )
        return ("generate", "edit")

    async def _generate_probe(
        self,
        provider: AbstractModelProvider,
        *,
        context: ModelCallContext,
        references: list[ReferenceImage],
        check: str,
    ) -> GeneratedImage:
        try:
            images = await provider.generate(
                context=context,
                prompt=_PROBE_PROMPT,
                negative_prompt="",
                reference_images=references,
                output=ImageOutputSpec(
                    ratio="1:1",
                    render_tier=RenderTier.STANDARD,
                    size=(1024, 1024),
                ),
                n=1,
                seed=0,
            )
        except Exception:
            raise CapabilityTestFailed(
                protocol=type(provider).__name__,
                check=check,
            ) from None
        if len(images) != 1:
            raise CapabilityTestFailed(
                protocol=type(provider).__name__,
                check=check,
            )
        return images[0]

    async def _probe_chat(
        self,
        record: ModelConfigRecord,
        credentials: dict[str, str | tuple[str, ...]],
        manager_id: str,
    ) -> tuple[str, ...]:
        try:
            provider = self.providers.build_text(
                record=record,
                credentials=credentials,
            )
            context = ModelCallContext(
                user_id=manager_id,
                operation=ModelOperation.CHAT_COMPLETION,
            )
            text_seen = False
            async for chunk in provider.complete(
                context=context,
                messages=[
                    ChatMessage(
                        role="system",
                        content="Run the configuration capability probe.",
                    ),
                    ChatMessage(
                        role="user",
                        content="Return a short text response.",
                    ),
                ],
                tools=[],
            ):
                if isinstance(chunk, TextChunk) and chunk.text:
                    text_seen = True
        except Exception:
            raise CapabilityTestFailed(
                protocol=record.provider_type.value,
                check="chat_protocol",
            ) from None
        if not text_seen:
            raise CapabilityTestFailed(
                protocol=record.provider_type.value,
                check="streamed_text",
            )

        try:
            valid_tool_seen = False
            async for chunk in provider.complete(
                context=context,
                messages=[
                    ChatMessage(
                        role="system",
                        content="Run the configuration capability probe.",
                    ),
                    ChatMessage(
                        role="user",
                        content="Call the probe tool.",
                    ),
                ],
                tools=[
                    ToolSpec(
                        name=_PROBE_TOOL,
                        description="Confirm tool-call capability.",
                        parameters={
                            "type": "object",
                            "properties": {
                                "ok": {"type": "boolean"}
                            },
                            "required": ["ok"],
                            "additionalProperties": False,
                        },
                        required=True,
                    )
                ],
            ):
                if isinstance(chunk, ToolCallChunk):
                    valid_tool_seen = any(
                        call.name == _PROBE_TOOL
                        and call.arguments == {"ok": True}
                        for call in chunk.tool_calls
                    )
        except Exception:
            raise CapabilityTestFailed(
                protocol=record.provider_type.value,
                check="chat_protocol",
            ) from None
        if not valid_tool_seen:
            raise CapabilityTestFailed(
                protocol=record.provider_type.value,
                check="tool_call",
            )
        return ("streamed_text", "tool_call")


class _ProbeImageStore(ImageStore):
    def __init__(self) -> None:
        self.images: dict[str, bytes] = {}

    async def save(
        self, data: bytes, *, suffix: str = ".png"
    ) -> StoredImage:
        if not data:
            raise ValueError("probe provider stored empty image bytes")
        key = f"probe-{len(self.images) + 1}{suffix}"
        self.images[key] = data
        return StoredImage(key=key, url=f"memory://{key}")

    async def load(self, image_key: str) -> bytes:
        return self.images[image_key]


def _deterministic_png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (1024, 1024), (192, 192, 192)).save(
        output,
        format="PNG",
    )
    return output.getvalue()


def _data_url(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode()
