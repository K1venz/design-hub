import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from design_hub.domain.enums import ModelType, ProviderType

GPT_IMAGE_2 = "gpt-image-2"
WAN_2_7_IMAGE_PRO = "wan2.7-image-pro"
DOUBAO_CHAT = "doubao-chat"

CredentialValue = str | tuple[str, ...]


@dataclass(frozen=True)
class ProviderRule:
    model_type: ModelType
    credential_fields: tuple[str, ...]
    required_credential_fields: tuple[str, ...]
    extra_fields: tuple[str, ...]


PROVIDER_RULES = {
    ProviderType.OPENAI_COMPAT_IMAGE: ProviderRule(
        model_type=ModelType.IMAGE,
        credential_fields=("standard_api_keys", "four_k_api_key"),
        required_credential_fields=("standard_api_keys",),
        extra_fields=("input_fidelity", "response_format"),
    ),
    ProviderType.DASHSCOPE_WAN_IMAGE: ProviderRule(
        model_type=ModelType.IMAGE,
        credential_fields=("api_key",),
        required_credential_fields=("api_key",),
        extra_fields=("watermark",),
    ),
    ProviderType.OPENAI_COMPAT_CHAT: ProviderRule(
        model_type=ModelType.CHAT,
        credential_fields=("api_key",),
        required_credential_fields=("api_key",),
        extra_fields=("thinking_disabled",),
    ),
}


def validate_connection_fields(
    *,
    model_type: ModelType,
    provider_type: ProviderType,
    base_url: str,
    upstream_model: str,
    extra: Mapping[str, object],
    credentials_plaintext: Mapping[str, CredentialValue],
) -> None:
    """Validate one complete, decrypted runtime connection before it is fingerprinted."""
    rule = PROVIDER_RULES[provider_type]
    if model_type is not rule.model_type:
        raise ValueError("invalid provider model type")
    if not base_url.strip() or not upstream_model.strip():
        raise ValueError("invalid provider connection")
    if set(credentials_plaintext).difference(rule.credential_fields):
        raise ValueError("invalid provider credential fields")
    if set(extra).difference(rule.extra_fields):
        raise ValueError("invalid provider extra fields")
    if any(field not in credentials_plaintext for field in rule.required_credential_fields):
        raise ValueError("invalid provider credential fields")
    if provider_type is ProviderType.OPENAI_COMPAT_IMAGE:
        standard_keys = credentials_plaintext["standard_api_keys"]
        if (
            not _is_nonempty_secret_tuple(standard_keys)
            or "four_k_api_key" in credentials_plaintext
            and not _is_nonempty_secret(credentials_plaintext["four_k_api_key"])
        ):
            raise ValueError("invalid provider credential fields")
    elif not _is_nonempty_secret(credentials_plaintext["api_key"]):
        raise ValueError("invalid provider credential fields")

    for field, extra_value in extra.items():
        if field in {"input_fidelity", "response_format"} and (
            not isinstance(extra_value, str) or not extra_value
        ):
            raise ValueError("invalid provider extra fields")
        if field in {"watermark", "thinking_disabled"} and type(extra_value) is not bool:
            raise ValueError("invalid provider extra fields")


def _is_nonempty_secret(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _is_nonempty_secret_tuple(value: object) -> bool:
    return isinstance(value, tuple) and bool(value) and all(
        _is_nonempty_secret(item) for item in value
    )


def connection_fingerprint(
    *,
    model_type: ModelType,
    provider_type: ProviderType,
    base_url: str,
    upstream_model: str,
    extra: Mapping[str, object],
    credentials_plaintext: Mapping[str, CredentialValue],
) -> str:
    """Return the stable, secret-safe identity of a validated live connection."""
    validate_connection_fields(
        model_type=model_type,
        provider_type=provider_type,
        base_url=base_url,
        upstream_model=upstream_model,
        extra=extra,
        credentials_plaintext=credentials_plaintext,
    )
    credential_digests: dict[str, str | list[str]] = {}
    for key, value in sorted(credentials_plaintext.items()):
        if isinstance(value, tuple):
            credential_digests[key] = [
                hashlib.sha256(item.encode()).hexdigest() for item in value
            ]
        else:
            credential_digests[key] = hashlib.sha256(value.encode()).hexdigest()
    payload = {
        "base_url": base_url.strip().rstrip("/"),
        "credentials": credential_digests,
        "extra": dict(sorted(extra.items())),
        "model": upstream_model,
        "model_type": model_type.value,
        "provider_type": provider_type.value,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
