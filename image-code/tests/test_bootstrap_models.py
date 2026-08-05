import asyncio
import json
from collections.abc import AsyncIterator, Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.ext.asyncio import AsyncEngine

from design_hub.application.admin.model_capability_service import (
    CapabilityProviderFactory,
    ModelCapabilityService,
)
from design_hub.application.admin.model_config_service import ModelConfigService
from design_hub.cli import bootstrap_models
from design_hub.cli.bootstrap_models import (
    BootstrapInputError,
    BootstrapModelFailed,
    ModelBootstrap,
    load_bootstrap_plan,
)
from design_hub.domain.enums import ModelType, ProviderType
from design_hub.domain.image_capabilities import ImageOutputSpec
from design_hub.domain.model_config import DOUBAO_CHAT, GPT_IMAGE_2, WAN_2_7_IMAGE_PRO
from design_hub.domain.models import GeneratedImage, ReferenceImage
from design_hub.domain.nano_banana import (
    NANO_BANANA_2_MODEL_ID,
    NANO_BANANA_UPSTREAM_MODEL,
)
from design_hub.infrastructure.db.base import Base
from design_hub.infrastructure.db.model_config_repo import SqlAlchemyModelConfigRepository
from design_hub.infrastructure.db.models import ModelConfig, ModelDefault
from design_hub.infrastructure.db.session import create_engine, create_session_factory
from design_hub.infrastructure.security.model_verification import (
    PyJwtModelVerificationService,
)
from design_hub.ports.image_store import ImageStore
from design_hub.ports.model_calls import ModelCallContext
from design_hub.ports.model_config_repository import ModelConfigRecord
from design_hub.ports.model_provider import AbstractModelProvider
from design_hub.ports.text_llm import (
    ChatMessage,
    LLMChunk,
    TextChunk,
    TextLLMPort,
    ToolCall,
    ToolCallChunk,
    ToolSpec,
)

_MODEL_IDS = (
    GPT_IMAGE_2,
    NANO_BANANA_2_MODEL_ID,
    WAN_2_7_IMAGE_PRO,
    DOUBAO_CHAT,
)
_WAN_HOST = "https://dashscope.aliyuncs.com"
_WAN_PATH = "/api/v1"


def _private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _environment(private_key_pem: str) -> dict[str, str]:
    return {
        "AUTH_RSA_PRIVATE_KEY_PEM": private_key_pem,
        "GPT_IMAGE_BASE_URL": "https://gpt.example.test/v1/",
        "GPT_IMAGE_API_KEY": "gpt-standard-first,gpt-standard-second",
        "GPT_IMAGE_4K_API_KEY": "gpt-four-k",
        "GPT_IMAGE_MODEL": "gpt-upstream",
        "GPT_IMAGE_INPUT_FIDELITY": "high",
        "GPT_IMAGE_RESPONSE_FORMAT": "b64_json",
        "NANO_BANANA_BASE_URL": "https://gemini.example.test/",
        "NANO_BANANA_API_KEYS": "nano-first,nano-second",
        "NANO_BANANA_MODEL": NANO_BANANA_UPSTREAM_MODEL,
        "TEXT_LLM_BASE_URL": "https://chat.example.test/v1/",
        "TEXT_LLM_API_KEY": "doubao-secret",
        "TEXT_LLM_MODEL": "doubao-upstream",
        "TEXT_LLM_THINKING_DISABLED": "true",
    }


def _write_wan_csv(path: Path, *, rows: list[tuple[str, ...]] | None = None) -> str:
    selected = rows or [
        ("apiKey", "wan-secret"),
        ("apiHost", _WAN_HOST),
        ("dashScope", _WAN_PATH),
    ]
    content = "".join(",".join(row) + "\n" for row in selected)
    path.write_text(content, encoding="utf-8")
    return content


class _ImageProvider(AbstractModelProvider):
    reference_mode = "bytes"

    def __init__(self, *, name: str, image_store: ImageStore) -> None:
        self.name = name
        self.unit_cost = Decimal("0")
        self._image_store = image_store

    async def generate(
        self,
        *,
        context: ModelCallContext,
        prompt: str,
        negative_prompt: str,
        reference_images: list[ReferenceImage],
        output: ImageOutputSpec,
        n: int,
        seed: int | None = None,
        quality: str | None = None,
    ) -> list[GeneratedImage]:
        stored = await self._image_store.save(b"probe-image")
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
            yield TextChunk("ok")
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


class _CapabilityFactory(CapabilityProviderFactory):
    def __init__(self, *, failing_model: str | None = None) -> None:
        self.failing_model = failing_model
        self.connections: list[
            tuple[ModelConfigRecord, dict[str, str | tuple[str, ...]]]
        ] = []

    def build_image(
        self,
        *,
        record: ModelConfigRecord,
        credentials: dict[str, str | tuple[str, ...]],
        image_store: ImageStore,
    ) -> AbstractModelProvider:
        self.connections.append((record, credentials))
        if record.name == self.failing_model:
            raise RuntimeError("upstream body with wan-secret")
        return _ImageProvider(name=record.name, image_store=image_store)

    def build_text(
        self,
        *,
        record: ModelConfigRecord,
        credentials: dict[str, str | tuple[str, ...]],
    ) -> TextLLMPort:
        self.connections.append((record, credentials))
        if record.name == self.failing_model:
            raise RuntimeError("upstream body with doubao-secret")
        return _ChatProvider()


async def _services(
    tmp_path: Path,
    *,
    cipher: Any,
    factory: _CapabilityFactory,
) -> tuple[ModelBootstrap, SqlAlchemyModelConfigRepository, AsyncEngine]:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'bootstrap.db'}")
    sessions = create_session_factory(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        session.add_all(
            [
                ModelConfig(
                    name=NANO_BANANA_2_MODEL_ID,
                    display_name="Nano Banana 2",
                    model_type=ModelType.IMAGE.value,
                    provider_type=ProviderType.GEMINI_NATIVE_IMAGE.value,
                    base_url="",
                    model=NANO_BANANA_UPSTREAM_MODEL,
                    credentials_ciphertext={},
                    unit_cost=Decimal("0.10"),
                    enabled=False,
                    revision=1,
                    verified_at=None,
                    verified_fingerprint=None,
                    extra={},
                ),
                ModelConfig(
                    name=GPT_IMAGE_2,
                    display_name="GPT Image",
                    model_type=ModelType.IMAGE.value,
                    provider_type=ProviderType.OPENAI_COMPAT_IMAGE.value,
                    base_url="",
                    model=GPT_IMAGE_2,
                    credentials_ciphertext={},
                    unit_cost=Decimal("0.05"),
                    enabled=False,
                    revision=1,
                    verified_at=None,
                    verified_fingerprint=None,
                    extra={},
                ),
                ModelConfig(
                    name=WAN_2_7_IMAGE_PRO,
                    display_name="Wan",
                    model_type=ModelType.IMAGE.value,
                    provider_type=ProviderType.DASHSCOPE_WAN_IMAGE.value,
                    base_url="",
                    model=WAN_2_7_IMAGE_PRO,
                    credentials_ciphertext={},
                    unit_cost=Decimal("0.50"),
                    enabled=False,
                    revision=1,
                    verified_at=None,
                    verified_fingerprint=None,
                    extra={},
                ),
                ModelConfig(
                    name=DOUBAO_CHAT,
                    display_name="Doubao",
                    model_type=ModelType.CHAT.value,
                    provider_type=ProviderType.OPENAI_COMPAT_CHAT.value,
                    base_url="",
                    model=DOUBAO_CHAT,
                    credentials_ciphertext={},
                    unit_cost=Decimal("0"),
                    enabled=False,
                    revision=1,
                    verified_at=None,
                    verified_fingerprint=None,
                    extra={},
                ),
                ModelDefault(
                    model_type=ModelType.IMAGE.value,
                    model_name=GPT_IMAGE_2,
                ),
                ModelDefault(
                    model_type=ModelType.CHAT.value,
                    model_name=DOUBAO_CHAT,
                ),
            ]
        )
        await session.commit()
    repository = SqlAlchemyModelConfigRepository(sessions)
    verifier = PyJwtModelVerificationService(
        secret="bootstrap-test-secret-at-least-32-bytes",
        ttl_seconds=60,
    )
    config_service = ModelConfigService(
        repo=repository,
        cipher=cipher,
        verifier=verifier,
    )
    capability_service = ModelCapabilityService(
        repository=repository,
        cipher=cipher,
        verifier=verifier,
        providers=factory,
    )
    return (
        ModelBootstrap(
            configs=config_service,
            capabilities=capability_service,
            actor_id=0,
        ),
        repository,
        engine,
    )


def _print_status(model_id: str, succeeded: bool) -> None:
    print(f"{model_id}: {'success' if succeeded else 'failure'}")


def _ciphertexts(records: list[ModelConfigRecord]) -> list[str]:
    ciphertexts: list[str] = []
    for record in records:
        for value in record.credentials_ciphertext.values():
            ciphertexts.extend(value if isinstance(value, list) else [value])
    return ciphertexts


def _assert_streams_are_secret_safe(
    output: str,
    *,
    csv_path: Path,
    csv_content: str,
    plaintext: list[str],
    ciphertext: list[str],
) -> None:
    assert str(csv_path) not in output
    assert csv_content not in output
    for value in [*plaintext, *ciphertext]:
        assert value not in output


def test_bootstrap_encrypts_each_connection_field_and_enables_verified_models(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def run() -> None:
        csv_path = tmp_path / "private-wan.csv"
        csv_content = _write_wan_csv(csv_path)
        environment = _environment(_private_key_pem())
        plan = load_bootstrap_plan(wan_csv=csv_path, environ=environment)
        factory = _CapabilityFactory()
        bootstrap, repository, engine = await _services(
            tmp_path,
            cipher=plan.cipher,
            factory=factory,
        )
        try:
            await bootstrap.run(plan.models, report=_print_status)
            records = await repository.list_all()
            by_name = {record.name: record for record in records}

            assert [record.name for record, _credentials in factory.connections] == list(
                _MODEL_IDS
            )
            gpt_record, gpt_credentials = factory.connections[0]
            assert (
                gpt_record.base_url,
                gpt_record.model,
                gpt_credentials,
                gpt_record.extra,
            ) == (
                "https://gpt.example.test/v1",
                "gpt-upstream",
                {
                    "standard_api_keys": (
                        "gpt-standard-first",
                        "gpt-standard-second",
                    ),
                    "four_k_api_key": "gpt-four-k",
                },
                {
                    "input_fidelity": "high",
                    "response_format": "b64_json",
                },
            )
            nano_record, nano_credentials = factory.connections[1]
            assert (
                nano_record.base_url,
                nano_record.model,
                nano_credentials,
                nano_record.extra,
            ) == (
                "https://gemini.example.test",
                NANO_BANANA_UPSTREAM_MODEL,
                {"api_keys": ("nano-first", "nano-second")},
                {},
            )
            wan_record, wan_credentials = factory.connections[2]
            assert (
                wan_record.base_url,
                wan_record.model,
                wan_credentials,
                wan_record.extra,
            ) == (
                "https://dashscope.aliyuncs.com/api/v1",
                WAN_2_7_IMAGE_PRO,
                {"api_key": "wan-secret"},
                {"watermark": False},
            )
            chat_record, chat_credentials = factory.connections[3]
            assert (
                chat_record.base_url,
                chat_record.model,
                chat_credentials,
                chat_record.extra,
            ) == (
                "https://chat.example.test/v1",
                "doubao-upstream",
                {"api_key": "doubao-secret"},
                {"thinking_disabled": True},
            )

            assert all(by_name[name].enabled for name in _MODEL_IDS)
            assert all(by_name[name].verified_at is not None for name in _MODEL_IDS)
            assert await repository.get_default(ModelType.IMAGE) == GPT_IMAGE_2
            assert await repository.get_default(ModelType.CHAT) == DOUBAO_CHAT

            stored_json = json.dumps(
                {
                    name: by_name[name].credentials_ciphertext
                    for name in _MODEL_IDS
                },
                sort_keys=True,
            )
            plaintext = [
                "gpt-standard-first",
                "gpt-standard-second",
                "gpt-four-k",
                "nano-first",
                "nano-second",
                "wan-secret",
                "doubao-secret",
            ]
            assert all(secret not in stored_json for secret in plaintext)
            assert [
                plan.cipher.decrypt(value)
                for value in by_name[GPT_IMAGE_2].credentials_ciphertext[
                    "standard_api_keys"
                ]
            ] == ["gpt-standard-first", "gpt-standard-second"]
            assert plan.cipher.decrypt(
                by_name[NANO_BANANA_2_MODEL_ID].credentials_ciphertext[
                    "api_keys"
                ][0]
            ) == "nano-first"
            assert plan.cipher.decrypt(
                by_name[NANO_BANANA_2_MODEL_ID].credentials_ciphertext[
                    "api_keys"
                ][1]
            ) == "nano-second"
            assert plan.cipher.decrypt(
                by_name[GPT_IMAGE_2].credentials_ciphertext["four_k_api_key"]
            ) == "gpt-four-k"
            assert plan.cipher.decrypt(
                by_name[WAN_2_7_IMAGE_PRO].credentials_ciphertext["api_key"]
            ) == "wan-secret"
            assert plan.cipher.decrypt(
                by_name[DOUBAO_CHAT].credentials_ciphertext["api_key"]
            ) == "doubao-secret"

            streams = capsys.readouterr()
            assert streams.out.splitlines() == [
                "gpt-image-2: success",
                "nano-banana-2: success",
                "wan2.7-image-pro: success",
                "doubao-chat: success",
            ]
            assert streams.err == ""
            _assert_streams_are_secret_safe(
                streams.out + streams.err,
                csv_path=csv_path,
                csv_content=csv_content,
                plaintext=plaintext,
                ciphertext=_ciphertexts(records),
            )
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_failed_real_check_stops_and_keeps_failing_model_disabled(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def run() -> None:
        csv_path = tmp_path / "private-wan.csv"
        csv_content = _write_wan_csv(csv_path)
        plan = load_bootstrap_plan(
            wan_csv=csv_path,
            environ=_environment(_private_key_pem()),
        )
        factory = _CapabilityFactory(failing_model=WAN_2_7_IMAGE_PRO)
        bootstrap, repository, engine = await _services(
            tmp_path,
            cipher=plan.cipher,
            factory=factory,
        )
        try:
            with pytest.raises(BootstrapModelFailed) as caught:
                await bootstrap.run(plan.models, report=_print_status)
            assert caught.value.model_id == WAN_2_7_IMAGE_PRO
            assert caught.value.__cause__ is None

            records = await repository.list_all()
            by_name = {record.name: record for record in records}
            assert by_name[GPT_IMAGE_2].enabled is True
            assert by_name[NANO_BANANA_2_MODEL_ID].enabled is True
            assert by_name[WAN_2_7_IMAGE_PRO].enabled is False
            assert by_name[DOUBAO_CHAT].enabled is False
            assert [record.name for record, _credentials in factory.connections] == [
                GPT_IMAGE_2,
                NANO_BANANA_2_MODEL_ID,
                WAN_2_7_IMAGE_PRO,
            ]

            streams = capsys.readouterr()
            assert streams.out.splitlines() == [
                "gpt-image-2: success",
                "nano-banana-2: success",
                "wan2.7-image-pro: failure",
            ]
            assert streams.err == ""
            _assert_streams_are_secret_safe(
                streams.out + streams.err,
                csv_path=csv_path,
                csv_content=csv_content,
                plaintext=[
                    "gpt-standard-first",
                    "gpt-standard-second",
                    "gpt-four-k",
                    "nano-first",
                    "nano-second",
                    "wan-secret",
                    "doubao-secret",
                ],
                ciphertext=_ciphertexts(records),
            )
        finally:
            await engine.dispose()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("environment_change", "csv_rows"),
    [
        (lambda values: values.pop("AUTH_RSA_PRIVATE_KEY_PEM"), None),
        (
            lambda _values: None,
            [
                ("apiHost", _WAN_HOST),
                ("dashScope", _WAN_PATH),
            ],
        ),
        (
            lambda _values: None,
            [("apiKey", "wan-secret"), ("invalid", "row", "shape")],
        ),
        (
            lambda _values: None,
            [
                ("apiKey", "wan-secret"),
                ("apiHost", "https://example.invalid"),
                ("dashScope", _WAN_PATH),
            ],
        ),
        (
            lambda _values: None,
            [
                ("apiKey", "wan-secret"),
                ("apiHost", _WAN_HOST),
                ("dashScope", "/compatible-mode/v1"),
            ],
        ),
    ],
    ids=[
        "missing-persistent-key",
        "missing-csv-field",
        "invalid-csv",
        "wrong-host",
        "wrong-path",
    ],
)
def test_invalid_bootstrap_input_fails_fast_without_exposing_input(
    tmp_path: Path,
    environment_change: Callable[[dict[str, str]], object],
    csv_rows: list[tuple[str, ...]] | None,
) -> None:
    csv_path = tmp_path / "private-wan.csv"
    csv_content = _write_wan_csv(csv_path, rows=csv_rows)
    environment = _environment(_private_key_pem())
    environment_change(environment)

    with pytest.raises(BootstrapInputError) as caught:
        load_bootstrap_plan(wan_csv=csv_path, environ=environment)

    assert caught.value.__cause__ is None
    rendered = str(caught.value)
    assert str(csv_path) not in rendered
    assert csv_content not in rendered
    for secret in (
        "wan-secret",
        "gpt-standard-first",
        "gpt-standard-second",
        "gpt-four-k",
        "nano-first",
        "nano-second",
        "doubao-secret",
    ):
        assert secret not in rendered


def test_main_sanitizes_unexpected_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv_path = tmp_path / "private-wan.csv"
    csv_content = _write_wan_csv(csv_path)
    environment = _environment(_private_key_pem())

    async def fail(
        plan: Any,
        *,
        report: Callable[[str, bool], None],
    ) -> None:
        ciphertext = plan.models[0].credentials["standard_api_keys"][0]
        raise RuntimeError(
            f"gpt-standard-first {ciphertext} {csv_content} {csv_path}"
        )

    monkeypatch.setattr(bootstrap_models, "execute_bootstrap", fail)

    assert (
        bootstrap_models.main(
            ["--wan-csv", str(csv_path)],
            environ=environment,
        )
        == 1
    )
    streams = capsys.readouterr()
    assert streams.out == ""
    assert streams.err == "bootstrap: failure\n"
    _assert_streams_are_secret_safe(
        streams.out + streams.err,
        csv_path=csv_path,
        csv_content=csv_content,
        plaintext=[
            "gpt-standard-first",
            "gpt-standard-second",
            "gpt-four-k",
            "nano-first",
            "nano-second",
            "wan-secret",
            "doubao-secret",
        ],
        ciphertext=[],
    )


@pytest.mark.parametrize(
    "upstream_model",
    ["gemini-3.1-flash-image-preview", "gemini-3-pro-image-preview"],
)
def test_bootstrap_rejects_preview_nano_models(
    tmp_path: Path,
    upstream_model: str,
) -> None:
    csv_path = tmp_path / "private-wan.csv"
    _write_wan_csv(csv_path)
    environment = _environment(_private_key_pem())
    environment["NANO_BANANA_MODEL"] = upstream_model

    with pytest.raises(BootstrapInputError):
        load_bootstrap_plan(wan_csv=csv_path, environ=environment)
