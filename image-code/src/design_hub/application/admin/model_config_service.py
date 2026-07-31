from __future__ import annotations

from builtins import list as BuiltinList
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from design_hub.domain.enums import ModelType, ProviderType
from design_hub.domain.errors import NotFoundError
from design_hub.domain.model_config import PROVIDER_RULES, CredentialValue, connection_fingerprint
from design_hub.ports.model_config_repository import ModelConfigRecord, ModelConfigRepository
from design_hub.ports.model_verification import ModelVerificationService
from design_hub.ports.secret_cipher import SecretCipher

CiphertextCredentials = dict[str, str | list[str]]


@dataclass
class ModelConfigService:
    repo: ModelConfigRepository
    cipher: SecretCipher
    verifier: ModelVerificationService

    async def list(self) -> list[ModelConfigRecord]:
        return await self.repo.list_all()

    async def default_name(self, model_type: ModelType) -> str | None:
        return await self.repo.get_default(model_type)

    async def create(
        self,
        *,
        actor_id: int,
        name: str,
        display_name: str,
        model_type: ModelType,
        provider_type: ProviderType,
        base_url: str,
        model: str,
        credentials: CiphertextCredentials,
        unit_cost: Decimal,
        enabled: bool,
        extra: Mapping[str, object],
        verification_proof: str,
    ) -> ModelConfigRecord:
        if unit_cost < 0:
            raise ValueError("invalid model configuration")
        normalized_name = _normalize_required_text(name)
        normalized_display_name = _normalize_required_text(display_name)
        normalized_model = _normalize_required_text(model)
        normalized_credentials = _validate_ciphertext_credentials(provider_type, credentials)
        normalized_base_url = _normalize_base_url(base_url)
        plaintext = _decrypt_credentials(self.cipher, normalized_credentials)
        fingerprint = _fingerprint(
            model_type=model_type,
            provider_type=provider_type,
            base_url=normalized_base_url,
            model=normalized_model,
            extra=extra,
            credentials=plaintext,
        )
        self.verifier.verify(
            verification_proof,
            manager_id=str(actor_id),
            model_id=normalized_name,
            model_type=model_type,
            fingerprint=fingerprint,
        )
        return await self.repo.create(
            actor_id=actor_id,
            record=ModelConfigRecord(
                name=normalized_name,
                display_name=normalized_display_name,
                model_type=model_type,
                provider_type=provider_type,
                base_url=normalized_base_url,
                model=normalized_model,
                credentials_ciphertext=normalized_credentials,
                unit_cost=unit_cost,
                enabled=enabled,
                revision=1,
                verified_at=datetime.now(UTC),
                verified_fingerprint=fingerprint,
                extra=dict(extra),
            ),
        )

    async def update(
        self,
        *,
        actor_id: int,
        name: str,
        display_name: str | None = None,
        model_type: ModelType | None = None,
        provider_type: ProviderType | None = None,
        base_url: str | None = None,
        model: str | None = None,
        credentials: CiphertextCredentials | None = None,
        unit_cost: Decimal | None = None,
        enabled: bool | None = None,
        extra: Mapping[str, object] | None = None,
        verification_proof: str | None = None,
    ) -> ModelConfigRecord:
        normalized_name = _normalize_required_text(name)
        current = await self.repo.get(normalized_name)
        if current is None:
            raise NotFoundError("model config not found")
        if unit_cost is not None and unit_cost < 0:
            raise ValueError("invalid model configuration")
        next_model_type = model_type if model_type is not None else current.model_type
        next_provider_type = provider_type if provider_type is not None else current.provider_type
        next_base_url = _normalize_base_url(base_url) if base_url is not None else current.base_url
        next_model = _normalize_required_text(model) if model is not None else current.model
        next_extra = dict(extra) if extra is not None else current.extra
        next_credentials = (
            _validate_ciphertext_credentials(next_provider_type, credentials)
            if credentials is not None
            else current.credentials_ciphertext
        )
        connection_changed = (
            next_model_type != current.model_type
            or next_provider_type != current.provider_type
            or next_base_url != current.base_url
            or next_model != current.model
            or next_extra != current.extra
            or next_credentials != current.credentials_ciphertext
        )
        verified_at: datetime | None
        verified_fingerprint: str | None
        if connection_changed:
            fingerprint = _fingerprint(
                model_type=next_model_type,
                provider_type=next_provider_type,
                base_url=next_base_url,
                model=next_model,
                extra=next_extra,
                credentials=_decrypt_credentials(self.cipher, next_credentials),
            )
            if verification_proof is None:
                raise ValueError("verification proof is required")
            self.verifier.verify(
                verification_proof,
                manager_id=str(actor_id),
                model_id=current.name,
                model_type=next_model_type,
                fingerprint=fingerprint,
            )
            verified_at = datetime.now(UTC)
            verified_fingerprint = fingerprint
        else:
            verified_at = current.verified_at
            verified_fingerprint = current.verified_fingerprint
        next_enabled = enabled if enabled is not None else current.enabled
        if next_enabled and not current.enabled:
            fingerprint = _fingerprint(
                model_type=next_model_type,
                provider_type=next_provider_type,
                base_url=next_base_url,
                model=next_model,
                extra=next_extra,
                credentials=_decrypt_credentials(self.cipher, next_credentials),
            )
            if verified_at is None or verified_fingerprint != fingerprint:
                raise ValueError("model must be verified before enabling")
        return await self.repo.update(
            actor_id=actor_id,
            record=ModelConfigRecord(
                name=current.name,
                display_name=(
                    _normalize_required_text(display_name)
                    if display_name is not None
                    else current.display_name
                ),
                model_type=next_model_type,
                provider_type=next_provider_type,
                base_url=next_base_url,
                model=next_model,
                credentials_ciphertext=next_credentials,
                unit_cost=unit_cost if unit_cost is not None else current.unit_cost,
                enabled=next_enabled,
                revision=current.revision + 1,
                verified_at=verified_at,
                verified_fingerprint=verified_fingerprint,
                extra=next_extra,
            ),
            expected_revision=current.revision,
        )

    async def delete(self, *, actor_id: int, name: str) -> None:
        await self.repo.delete(actor_id=actor_id, name=name)

    async def set_default(self, *, actor_id: int, name: str) -> ModelConfigRecord:
        current = await self.repo.get(name)
        if current is None:
            raise NotFoundError("model config not found")
        fingerprint = _record_fingerprint(self.cipher, current)
        if (
            not current.enabled
            or current.verified_at is None
            or current.verified_fingerprint != fingerprint
        ):
            raise ValueError("default model must be enabled and verified")
        return await self.repo.set_default(actor_id=actor_id, name=name)

    async def catalog(
        self, model_type: ModelType
    ) -> BuiltinList[dict[str, str | bool]]:
        default_name = await self.repo.get_default(model_type)
        catalog: BuiltinList[dict[str, str | bool]] = []
        for record in await self.repo.list_all():
            if (
                record.model_type is model_type
                and record.enabled
                and record.verified_at is not None
                and record.verified_fingerprint == _record_fingerprint(self.cipher, record)
            ):
                catalog.append(
                    {
                        "id": record.name,
                        "display_name": record.display_name,
                        "is_default": record.name == default_name,
                    }
                )
        return catalog


def _normalize_base_url(value: str) -> str:
    return value.strip().rstrip("/")


def _normalize_required_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("invalid model configuration")
    return normalized


def _validate_ciphertext_credentials(
    provider_type: ProviderType,
    credentials: Mapping[str, str | list[str]],
) -> CiphertextCredentials:
    rule = PROVIDER_RULES[provider_type]
    if set(credentials).difference(rule.credential_fields):
        raise ValueError("invalid provider credential fields")
    validated: CiphertextCredentials = {}
    for field, value in credentials.items():
        if field == "standard_api_keys":
            if (
                not isinstance(value, list)
                or not value
                or not all(isinstance(item, str) and item for item in value)
            ):
                raise ValueError("invalid provider credential fields")
            validated[field] = list(value)
        elif not isinstance(value, str) or not value:
            raise ValueError("invalid provider credential fields")
        else:
            validated[field] = value
    if any(field not in validated for field in rule.required_credential_fields):
        raise ValueError("invalid provider credential fields")
    return validated


def _decrypt_credentials(
    cipher: SecretCipher, credentials: CiphertextCredentials
) -> dict[str, CredentialValue]:
    plaintext: dict[str, CredentialValue] = {}
    for field, value in credentials.items():
        if isinstance(value, list):
            plaintext[field] = tuple(cipher.decrypt(item) for item in value)
        else:
            plaintext[field] = cipher.decrypt(value)
    return plaintext


def _fingerprint(
    *,
    model_type: ModelType,
    provider_type: ProviderType,
    base_url: str,
    model: str,
    extra: Mapping[str, object],
    credentials: Mapping[str, CredentialValue],
) -> str:
    return connection_fingerprint(
        model_type=model_type,
        provider_type=provider_type,
        base_url=base_url,
        upstream_model=model,
        extra=extra,
        credentials_plaintext=credentials,
    )


def _record_fingerprint(cipher: SecretCipher, record: ModelConfigRecord) -> str:
    return _fingerprint(
        model_type=record.model_type,
        provider_type=record.provider_type,
        base_url=record.base_url,
        model=record.model,
        extra=record.extra,
        credentials=_decrypt_credentials(cipher, record.credentials_ciphertext),
    )
