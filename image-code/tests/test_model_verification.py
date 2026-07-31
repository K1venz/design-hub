import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from unittest.mock import patch

import jwt
import pytest

from design_hub.domain import model_config
from design_hub.domain.enums import ModelType, ProviderType
from design_hub.infrastructure.security.model_verification import (
    PyJwtModelVerificationService,
)

_SECRET = "test-model-verification-secret-32-bytes"


@dataclass(frozen=True)
class _Draft:
    display_name: str
    unit_cost: Decimal
    model_type: ModelType = ModelType.IMAGE
    provider_type: ProviderType = ProviderType.OPENAI_COMPAT_IMAGE
    base_url: str = "https://images.example.test/v1/"
    upstream_model: str = "upstream-image-v2"
    extra: dict[str, object] | None = None
    credentials: dict[str, str | tuple[str, ...]] | None = None

    def fingerprint(self) -> str:
        return model_config.connection_fingerprint(
            model_type=self.model_type,
            provider_type=self.provider_type,
            base_url=self.base_url,
            upstream_model=self.upstream_model,
            extra=self.extra or {"response_format": "b64_json", "input_fidelity": "high"},
            credentials_plaintext=self.credentials
            or {"four_k_api_key": "four-k-secret", "standard_api_keys": ("key-a", "key-b")},
        )


def test_connection_fingerprint_is_order_independent_and_ignores_display_fields() -> None:
    first = _Draft(display_name="GPT Image", unit_cost=Decimal("0.05"))
    second = _Draft(
        display_name="Renamed image model",
        unit_cost=Decimal("99.99"),
        extra={"input_fidelity": "high", "response_format": "b64_json"},
        credentials={"standard_api_keys": ("key-a", "key-b"), "four_k_api_key": "four-k-secret"},
    )

    assert first.fingerprint() == second.fingerprint()


@pytest.mark.parametrize(
    "updates",
    [
        {"base_url": "https://other.example.test/v1/"},
        {"upstream_model": "another-upstream-model"},
        {
            "provider_type": ProviderType.DASHSCOPE_WAN_IMAGE,
            "extra": {"watermark": False},
            "credentials": {"api_key": "wan-secret"},
        },
        {"extra": {"response_format": "url", "input_fidelity": "high"}},
        {
            "credentials": {
                "four_k_api_key": "four-k-secret",
                "standard_api_keys": ("key-a", "key-c"),
            }
        },
    ],
)
def test_connection_fingerprint_changes_when_runtime_connection_changes(
    updates: dict[str, object],
) -> None:
    original = _Draft(display_name="GPT Image", unit_cost=Decimal("0.05"))
    changed = _Draft(**{**original.__dict__, **updates})  # type: ignore[arg-type]

    assert original.fingerprint() != changed.fingerprint()


def test_connection_fingerprint_hashes_secret_before_canonical_json() -> None:
    plaintext = "secret-never-in-canonical-json"
    captured_payloads: list[object] = []
    real_dumps = json.dumps

    def capture(value: object, *args: object, **kwargs: object) -> str:
        captured_payloads.append(value)
        return real_dumps(value, *args, **kwargs)

    with patch("design_hub.domain.model_config.json.dumps", side_effect=capture):
        model_config.connection_fingerprint(
            model_type=ModelType.CHAT,
            provider_type=ProviderType.OPENAI_COMPAT_CHAT,
            base_url="https://chat.example.test/v1",
            upstream_model="chat-v1",
            extra={"thinking_disabled": True},
            credentials_plaintext={"api_key": plaintext},
        )

    assert captured_payloads == [
        {
            "base_url": "https://chat.example.test/v1",
            "credentials": {"api_key": hashlib.sha256(plaintext.encode()).hexdigest()},
            "extra": {"thinking_disabled": True},
            "model": "chat-v1",
            "model_type": "chat",
            "provider_type": "openai_compat_chat",
        }
    ]


@pytest.mark.parametrize(
    ("model_type", "provider_type", "extra", "credentials"),
    [
        (ModelType.IMAGE, ProviderType.OPENAI_COMPAT_IMAGE, {}, {"api_key": "nope"}),
        (ModelType.IMAGE, ProviderType.DASHSCOPE_WAN_IMAGE, {"unknown": True}, {"api_key": "key"}),
        (ModelType.CHAT, ProviderType.OPENAI_COMPAT_CHAT, {}, {"unknown": "key"}),
    ],
)
def test_connection_fingerprint_rejects_provider_fields_outside_the_allowlist(
    model_type: ModelType,
    provider_type: ProviderType,
    extra: dict[str, object],
    credentials: dict[str, str | tuple[str, ...]],
) -> None:
    with pytest.raises(ValueError, match="invalid provider"):
        model_config.connection_fingerprint(
            model_type=model_type,
            provider_type=provider_type,
            base_url="https://provider.example.test/v1",
            upstream_model="model-v1",
            extra=extra,
            credentials_plaintext=credentials,
        )


def _service() -> PyJwtModelVerificationService:
    return PyJwtModelVerificationService(secret=_SECRET, ttl_seconds=600)


def _proof() -> tuple[PyJwtModelVerificationService, str]:
    service = _service()
    proof = service.issue(
        manager_id="manager-7",
        model_id="gpt-image-2",
        model_type=ModelType.IMAGE,
        fingerprint="a" * 64,
    )
    return service, proof


def test_verification_proof_validates_the_exact_manager_model_type_and_fingerprint() -> None:
    service, proof = _proof()

    service.verify(
        proof,
        manager_id="manager-7",
        model_id="gpt-image-2",
        model_type=ModelType.IMAGE,
        fingerprint="a" * 64,
    )

    for changes in (
        {"manager_id": "manager-8"},
        {"model_id": "wan2.7-image-pro"},
        {"model_type": ModelType.CHAT},
        {"fingerprint": "b" * 64},
    ):
        with pytest.raises(ValueError, match="invalid verification proof"):
            service.verify(
                proof,
                manager_id=changes.get("manager_id", "manager-7"),  # type: ignore[arg-type]
                model_id=changes.get("model_id", "gpt-image-2"),  # type: ignore[arg-type]
                model_type=changes.get("model_type", ModelType.IMAGE),  # type: ignore[arg-type]
                fingerprint=changes.get("fingerprint", "a" * 64),  # type: ignore[arg-type]
            )


def test_verification_proof_rejects_expired_and_tampered_tokens() -> None:
    service, proof = _proof()
    expired = jwt.encode(
        {
            "aud": "model-config-verification",
            "manager_id": "manager-7",
            "model_id": "gpt-image-2",
            "model_type": "image",
            "fingerprint": "a" * 64,
            "exp": 0,
        },
        _SECRET,
        algorithm="HS256",
    )
    tampered = f"{proof[:-1]}{'a' if proof[-1] != 'a' else 'b'}"

    for invalid in (expired, tampered):
        with pytest.raises(ValueError, match="invalid verification proof"):
            service.verify(
                invalid,
                manager_id="manager-7",
                model_id="gpt-image-2",
                model_type=ModelType.IMAGE,
                fingerprint="a" * 64,
            )
