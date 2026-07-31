from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from design_hub.domain.enums import ModelType, ProviderType
from design_hub.domain.model_config import PROVIDER_RULES
from design_hub.ports.model_config_repository import ModelConfigRecord


class ModelCredentialStatusOut(BaseModel):
    has_credentials: bool
    configured_fields: dict[str, bool]


class ModelConfigOut(BaseModel):
    name: str
    display_name: str
    model_type: ModelType
    provider_type: ProviderType
    base_url: str
    model: str
    unit_cost: Decimal
    enabled: bool
    is_default: bool
    revision: int
    verified_at: datetime | None
    extra: dict[str, object]
    credentials: ModelCredentialStatusOut

    @classmethod
    def of(
        cls,
        record: ModelConfigRecord,
        *,
        is_default: bool = False,
    ) -> "ModelConfigOut":
        rule = PROVIDER_RULES[record.provider_type]
        configured_fields = {
            field: field in record.credentials_ciphertext
            for field in rule.required_credential_fields
        }
        return cls(
            name=record.name,
            display_name=record.display_name,
            model_type=record.model_type,
            provider_type=record.provider_type,
            base_url=record.base_url,
            model=record.model,
            unit_cost=record.unit_cost,
            enabled=record.enabled,
            is_default=is_default,
            revision=record.revision,
            verified_at=record.verified_at,
            extra=dict(record.extra),
            credentials=ModelCredentialStatusOut(
                has_credentials=bool(record.credentials_ciphertext),
                configured_fields=configured_fields,
            ),
        )


class ModelConfigCreate(BaseModel):
    name: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    model_type: ModelType
    provider_type: ProviderType
    base_url: str
    model: str
    credentials: dict[str, str | list[str]]
    unit_cost: Decimal = Field(ge=0)
    enabled: bool = False
    extra: dict[str, object] = Field(default_factory=dict)
    verification_proof: str = Field(min_length=1)


class ModelConfigUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1)
    model_type: ModelType | None = None
    provider_type: ProviderType | None = None
    base_url: str | None = None
    model: str | None = None
    credentials: dict[str, str | list[str]] | None = None
    unit_cost: Decimal | None = Field(default=None, ge=0)
    enabled: bool | None = None
    extra: dict[str, object] | None = None
    verification_proof: str | None = None


class ModelCapabilityTestIn(BaseModel):
    name: str = Field(min_length=1)
    existing_model_name: str | None = Field(
        default=None,
        min_length=1,
    )
    model_type: ModelType
    provider_type: ProviderType
    base_url: str
    model: str
    credentials: dict[str, str | list[str]] | None = None
    extra: dict[str, object] = Field(default_factory=dict)


class ModelCapabilityTestOut(BaseModel):
    verification_proof: str
    tested_at: datetime
    checks: list[str]
